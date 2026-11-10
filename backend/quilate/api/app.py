"""API local (só 127.0.0.1:8000) e WebSocket de preços. Os nomes de campo são o contrato com o front.

Os handlers são `async def` de propósito: a conexão SQLite do contexto pertence à thread do loop,
e `def` comum rodaria numa thread do pool.
"""
import csv
import json
import tempfile
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from quilate.ai.playbook import approve_rule, current_playbook, latest_draft
from quilate.ai.verdict import last_price
from quilate.api.setup import setup_router
from quilate.budget import budget_state, month_spent
from quilate.exchanges.client import UNVERIFIED
from quilate.exchanges.cost_basis import Trade, compute_cost_basis, unrealized_pnl
from quilate.exchanges.csv_import import parse_csv
from quilate.exchanges.sync import insert_trades
from quilate.market.collect import STABLES
from quilate.signals.inputs import daily_closes, dominance_7d_change, snapshot
from quilate.telegram.bot import DISCLAIMER
from quilate.track.record import hit_rates, outcomes

STATIC = Path(__file__).parent / "static"
PORT = 8000
DEV_ORIGINS = {"http://127.0.0.1:5173", "http://localhost:5173"}  # servidor do Vite em desenvolvimento
MAX_CSV = 5 * 1024 * 1024
HISTORY_DAYS, CANDLE_DAYS, QUOTES = 30, 90, 10
TIMELINE, LIVES, TRACK_LIST = 10, 10, 100
GROUPS = ("Sair", "Reduzir", "Manter")
SYMBOL = r"^[A-Z0-9]{1,15}$"
MARKET_SOURCES = {  # chave do snapshot -> fonte mostrada ao lado do número
    "fng": "Alternative.me", "cg_global": "CoinGecko", "alt_season": "Calculado a partir do CoinGecko",
    "btc_onchain": "BGeometrics", "derivs": "Coinalyze", "dxy": "FRED",
    "etf_flows": "TFTC", "stablecoins": "DefiLlama",
}
NO_FRONT = "O front ainda não foi construído. Rode o build do frontend para gerar quilate/api/static."


class LocalOnly:
    """Recusa Host fora dos 4 permitidos (antídoto de DNS rebinding) e Origin estranha no WebSocket
    e em requisições que alteram dados (CSRF). Sem Origin passa: navegador sempre manda, curl não.
    As listas saem da porta em que o servidor escuta (`servir --porta`)."""

    def __init__(self, app, port: int = PORT):
        self.app = app
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"}
        self.origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}", *DEV_ORIGINS}
        self.default_origin = f"http://127.0.0.1:{port}"

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            h = {k.decode("latin-1"): v.decode("latin-1").lower() for k, v in scope["headers"]}
            checks_origin = scope["type"] == "websocket" or scope["method"] not in ("GET", "HEAD", "OPTIONS")
            if h.get("host") not in self.hosts or (checks_origin and h.get("origin", self.default_origin) not in self.origins):
                if scope["type"] == "websocket":
                    return await WebSocket(scope, receive, send).close(code=1008)
                return await PlainTextResponse("Acesso negado.", status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)


class CostOverride(BaseModel):
    symbol: str = Field(pattern=SYMBOL)
    avg_cost_usd: float = Field(gt=0, allow_inf_nan=False)
    qty: float | None = Field(None, gt=0, allow_inf_nan=False)
    note: str | None = Field(None, max_length=500)


def create_app(ctx, static_dir: Path = STATIC, port: int = PORT, local_config: Path | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # sem CORS de propósito
    app.add_middleware(LocalOnly, port=port)
    app.include_router(setup_router(ctx, local_config))  # antes da rota pega-tudo do front
    conn, tz = ctx.conn, ctx.settings.tz

    def today() -> date:
        return datetime.now(ZoneInfo(tz)).date()

    def price(sym: str) -> float | None:
        if sym in STABLES:
            return 1.0
        try:
            return last_price(ctx, sym, today())  # ao vivo, senão o último fechamento
        except ValueError:
            return None

    def holdings() -> dict[str, dict]:
        coins: dict[str, dict] = {}
        for r in conn.execute("SELECT exchange, symbol, wallet, qty, stale FROM positions WHERE qty > 0 "
                              "ORDER BY exchange, symbol, wallet"):
            c = coins.setdefault(r["symbol"], {"qty": 0.0, "rows": []})
            c["qty"] += r["qty"]
            c["rows"].append(r)
        for sym, c in coins.items():
            c["price"] = price(sym)
        return coins

    def basis(sym: str, qty: float):
        trades = [Trade(**{**dict(r), "ts_utc": datetime.fromisoformat(r["ts_utc"])})
                  for r in conn.execute("SELECT * FROM trades WHERE symbol=?", (sym,))]
        ov = conn.execute("SELECT avg_cost_usd FROM cost_overrides WHERE symbol=?", (sym,)).fetchone()
        return compute_cost_basis(trades, qty, ov[0] if ov else None)

    def history(coins: dict[str, dict]) -> list[dict]:
        """Valor da carteira atual (quantidade de hoje) a preço de fechamento dos últimos 30 dias.
        Aproximação: as posições são as de hoje, não as de cada dia. Dia sem candle usa o último fechamento."""
        series = {}
        for sym, c in coins.items():
            cl = {} if sym in STABLES else daily_closes(conn, sym, today())
            series[sym] = (c["qty"], cl, sorted(cl))
        out = []
        for i in range(HISTORY_DAYS - 1, -1, -1):
            d = (today() - timedelta(days=i)).isoformat()
            total = 0.0
            for sym, (qty, cl, keys) in series.items():
                if sym in STABLES:
                    total += qty
                elif (j := bisect_right(keys, d) - 1) >= 0:
                    total += qty * cl[keys[j]]
            if total:
                out.append({"ts": d, "usd": total})
        return out

    def usdbrl() -> float | None:
        """Câmbio só do snapshot `usdbrl` (número ou {"usdbrl": n}); sem ele, null. Nenhuma taxa fixa no código."""
        v = snapshot(conn, "usdbrl", today())
        v = v.get("usdbrl") if isinstance(v, dict) else v
        return float(v) if isinstance(v, int | float) else None

    @app.get("/api/overview")
    async def overview():
        coins = holdings()
        by_ex: dict[str, dict] = {}
        total = invested = pnl = 0.0
        for sym, c in coins.items():
            if c["price"] is None:
                continue
            total += c["qty"] * c["price"]
            for r in c["rows"]:
                e = by_ex.setdefault(r["exchange"], {"exchange": r["exchange"], "usd": 0.0, "stale": False})
                e["usd"] += r["qty"] * c["price"]
                e["stale"] |= bool(r["stale"])
            b = basis(sym, c["qty"]) if sym not in STABLES else None
            if b and b.avg_cost_usd is not None:
                invested += b.avg_cost_usd * c["qty"]
                pnl += unrealized_pnl(b, c["price"])
        now = datetime.now(UTC)
        last = conn.execute("SELECT MAX(created_utc) FROM verdicts WHERE trigger='diario'").fetchone()[0]
        pb = current_playbook(conn)
        rate = usdbrl()
        return {
            "total_usd": total, "total_brl": total * rate if rate else None,
            "invested_usd": invested, "pnl_usd": pnl, "pnl_pct": pnl / invested if invested else None,  # fração
            "by_exchange": [{**e, "share": e["usd"] / total if total else 0.0}
                            for e in sorted(by_ex.values(), key=lambda e: -e["usd"])],
            "history": history(coins),
            "spent_month_usd": month_spent(conn, now, tz), "budget_usd": ctx.settings.budget_usd,
            "budget_state": budget_state(conn, ctx.settings, now), "last_cycle_utc": last,
            "playbook_approved": bool(pb and pb.approved), "disclaimer": DISCLAIMER,
            "analyst_name": ctx.settings.analyst_name,
        }

    def card(v, coins: dict[str, dict], names: dict) -> dict:
        sym = v["symbol"]
        h = coins.get(sym)
        qty = h["qty"] if h else 0.0
        px = (h["price"] if h else None) or v["price_usd"]
        b = basis(sym, qty) if h else None
        pros, cons = json.loads(v["pros_json"]), json.loads(v["cons_json"])
        signals = json.loads(v["signals_json"])
        ref = daily_closes(conn, sym, today()).get((today() - timedelta(days=1)).isoformat()) if sym not in STABLES else None
        return {
            "symbol": sym, "name": (names.get(sym) or {}).get("name") or sym,
            "exchanges": sorted({r["exchange"] for r in h["rows"]}) if h else [],
            "price_usd": px, "change_24h": px / ref - 1 if ref else None, "value_usd": qty * px,
            "pnl_usd": unrealized_pnl(b, px) if b else None, "cost_unknown": bool(b and b.unknown),
            "verdict": v["final_verdict"], "rubric_verdict": v["rubric_verdict"], "ai_verdict": v["ai_verdict"],
            "confidence": v["confidence"], "alerts": sum(1 for s in signals if s["alert"]),  # quantos dos 7 sinais em alerta
            "signals": [{k: s[k] for k in ("code", "name", "alert", "value")} for s in signals],
            "reason": next(iter(pros if v["final_verdict"] == "Manter" else cons), ""),
            "no_analyst": bool(v["no_analyst"]), "flag": v["flag"],
            "_pros": pros, "_cons": cons, "_risk": v["main_risk"], "_basis": b, "_qty": qty,
        }

    def public(c: dict) -> dict:
        return {k: x for k, x in c.items() if not k.startswith("_")}

    def names() -> dict:
        return snapshot(conn, "cg_assets", date.max) or {}

    @app.get("/api/verdicts")
    async def verdicts(day: date | None = None):
        d = day.isoformat() if day else (conn.execute("SELECT MAX(day) FROM verdicts").fetchone()[0] or today().isoformat())
        rows = conn.execute(
            "SELECT * FROM verdicts v WHERE day=? AND id = (SELECT id FROM verdicts WHERE day=v.day AND symbol=v.symbol "
            "ORDER BY created_utc DESC, id DESC LIMIT 1)", (d,)).fetchall()
        coins, nm = holdings(), names()
        cards = sorted((card(v, coins, nm) for v in rows), key=lambda c: -c["value_usd"])
        return {"day": d, "groups": {g: [public(c) for c in cards if c["verdict"] == g] for g in GROUPS}}

    def quotes(sym: str) -> list[dict]:
        out = []
        for r in conn.execute(
                "SELECT m.msg_id, m.text, m.topic_id, m.media_kind, m.date_utc, men.chunk_id, c.source_kind, "
                "c.text AS ctext, c.t_start FROM mentions men JOIN messages m ON m.msg_id = men.msg_id "
                "LEFT JOIN chunks c ON c.id = men.chunk_id WHERE men.symbol=? AND men.is_analyst=1 "
                "ORDER BY m.date_utc DESC, men.id DESC LIMIT ?", (sym, QUOTES)):
            if r["source_kind"] in ("transcricao", "link"):
                kind, text, t_start, qid = r["source_kind"], r["ctext"], r["t_start"], f"c:{r['chunk_id']}"
            else:
                kind = {"foto": "foto", "audio": "audio"}.get(r["media_kind"], "texto")
                text, t_start, qid = r["text"], None, f"m:{r['msg_id']}"
            out.append({"id": qid, "text": text or "", "date_utc": r["date_utc"],
                        "topic": ctx.settings.group_topics.get(r["topic_id"]), "kind": kind, "t_start": t_start})
        return out

    @app.get("/api/coins/{symbol}")
    async def coin(symbol: str = PathParam(pattern=SYMBOL)):
        v = conn.execute("SELECT * FROM verdicts WHERE symbol=? ORDER BY day DESC, created_utc DESC, id DESC LIMIT 1",
                         (symbol,)).fetchone()
        if v is None:
            raise HTTPException(404, "Moeda sem veredito.")
        coins = holdings()
        c = card(v, coins, names())
        floor = (today() - timedelta(days=CANDLE_DAYS)).isoformat()
        return {**public(c), "avg_cost_usd": c["_basis"].avg_cost_usd if c["_basis"] else None, "qty": c["_qty"],
                "by_exchange": [{"exchange": r["exchange"], "wallet": r["wallet"], "qty": r["qty"]}
                                for r in (coins[symbol]["rows"] if symbol in coins else [])],
                "candles": [{"day": d, "close": x} for d, x in sorted(daily_closes(conn, symbol, today()).items()) if d >= floor],
                "pros": c["_pros"], "cons": c["_cons"], "main_risk": c["_risk"], "quotes": quotes(symbol)}

    @app.get("/api/portfolio")
    async def portfolio():
        coins, nm = holdings(), names()
        total = sum(c["qty"] * c["price"] for c in coins.values() if c["price"] is not None)
        out = []
        for sym, c in coins.items():
            b = basis(sym, c["qty"]) if sym not in STABLES else None
            value = c["qty"] * c["price"] if c["price"] is not None else None
            out.append({
                "symbol": sym, "name": (nm.get(sym) or {}).get("name") or sym, "qty": c["qty"],
                "price_usd": c["price"], "value_usd": value, "share": value / total if value is not None and total else None,
                "avg_cost_usd": b.avg_cost_usd if b else None, "cost_unknown": bool(b and b.unknown),
                "pnl_usd": unrealized_pnl(b, c["price"]) if b and c["price"] is not None else None,
                "exchanges": sorted({r["exchange"] for r in c["rows"]}),
                "positions": [{"exchange": r["exchange"], "wallet": r["wallet"], "qty": r["qty"],
                               "stale": bool(r["stale"]), "permissions_verified": r["exchange"] not in UNVERIFIED}
                              for r in c["rows"]]})
        return {"total_usd": total, "coins": sorted(out, key=lambda x: -(x["value_usd"] or 0))}

    @app.get("/api/market")
    async def market():
        out = {}
        for key, source in MARKET_SOURCES.items():
            row = conn.execute("SELECT day, value_json FROM snapshots WHERE key=? ORDER BY day DESC LIMIT 1", (key,)).fetchone()
            out[key] = {"day": row["day"], "source": source, "value": json.loads(row["value_json"])} if row else None
        if out["cg_global"]:  # pontos percentuais; None sem os 7 snapshots diários
            out["cg_global"]["change_7d"] = dominance_7d_change(conn, date.fromisoformat(out["cg_global"]["day"]))
        return out

    @app.get("/api/track")
    async def track():
        outs = outcomes(conn, today())
        days = dict(conn.execute("SELECT id, day FROM verdicts").fetchall())
        listed: dict[int, dict] = {}
        for o in outs:
            v = listed.setdefault(o.verdict_id, {"id": o.verdict_id, "day": days[o.verdict_id], "symbol": o.symbol,
                                                 "verdict": o.verdict, "outcomes": {}})
            v["outcomes"][str(o.horizon)] = {"r_hold": o.r_hold, "r_paper": o.r_paper, "r_btc": o.r_btc, "hit": o.hit}
        # ponytail: só os TRACK_LIST mais recentes; paginar se a lista inteira fizer falta
        recent = sorted(listed.values(), key=lambda v: (v["day"], v["symbol"]), reverse=True)[:TRACK_LIST]
        return {**hit_rates(outs), "verdicts": recent}  # chaves de horizonte viram texto no JSON

    def sources(ids: set[str]) -> dict[str, dict]:
        """Fontes citadas nas regras (m:<msg_id> ou c:<chunk_id>). Id que sumiu do banco fica de fora."""
        def nums(prefix: str) -> list[int]:
            return [int(i[2:]) for i in ids if i.startswith(prefix) and i[2:].isdigit()]

        def marks(n: list[int]) -> str:
            return ",".join("?" * len(n))

        out = {}
        m = nums("m:")
        for r in conn.execute(f"SELECT msg_id, topic_id, date_utc, text, media_kind FROM messages WHERE msg_id IN ({marks(m)})", m):
            out[f"m:{r['msg_id']}"] = {"date_utc": r["date_utc"], "topic": ctx.settings.group_topics.get(r["topic_id"]),
                                       "kind": {"foto": "foto", "audio": "audio"}.get(r["media_kind"], "texto"),
                                       "text": r["text"] or "", "url": None, "t_start": None}
        c = nums("c:")
        for r in conn.execute(f"SELECT id, source_kind, source_id, text, t_start, date_utc FROM chunks WHERE id IN ({marks(c)})", c):
            ref, t = r["source_id"], r["t_start"]
            url = None
            if ref.startswith(("http://", "https://")):  # áudio enviado no grupo é arquivo local: sem link
                url = ref if r["source_kind"] == "link" or t is None else f"{ref}{'&' if '?' in ref else '?'}t={int(t)}s"
            out[f"c:{r['id']}"] = {"date_utc": r["date_utc"], "topic": None, "kind": r["source_kind"],
                                   "text": r["text"], "url": url, "t_start": t}
        return out

    @app.get("/api/playbook")
    async def playbook():
        pb = latest_draft(conn) or current_playbook(conn)  # o rascunho semanal aparece para aprovação; o veredito usa só a aprovada
        rules = [] if pb is None else [
            {"id": r["id"], "category": r["category"], "text": r["text"],
             "source_ids": json.loads(r["source_ids_json"]), "approved": bool(r["approved"])}
            for r in conn.execute("SELECT * FROM playbook_rules WHERE version_id=? ORDER BY id", (pb.version_id,))]
        topic = ctx.settings.trigger_topic  # 0: sem tópico de gatilho, a linha do tempo fica vazia
        timeline = [] if not topic else [
            {"id": f"m:{r['msg_id']}", "date_utc": r["date_utc"], "text": r["text"] or "",
             "kind": {"foto": "foto", "audio": "audio"}.get(r["media_kind"], "texto")}
            for r in conn.execute("SELECT msg_id, date_utc, text, media_kind FROM messages WHERE is_analyst=1 "
                                  "AND topic_id=? ORDER BY date_utc DESC LIMIT ?", (topic, TIMELINE))]
        lives = [{"url": r["ref"], "status": r["status"], "date_utc": r["date_utc"]}
                 for r in conn.execute("SELECT j.ref, j.status, m.date_utc FROM media_jobs j LEFT JOIN messages m "
                                       "ON m.msg_id = j.msg_id WHERE j.kind='youtube' "
                                       "ORDER BY m.date_utc DESC, j.id DESC LIMIT ?", (LIVES,))]
        return {"version_id": pb.version_id if pb else None, "markdown": pb.markdown if pb else "",
                "approved": bool(pb and pb.approved), "rules": rules,
                "sources": sources({i for r in rules for i in r["source_ids"]}), "timeline": timeline, "lives": lives,
                "trigger_topic_name": ctx.settings.group_topics.get(topic) if topic else None,
                "lives_count": dict(conn.execute("SELECT status, COUNT(*) FROM media_jobs WHERE kind='youtube' "
                                                 "GROUP BY status").fetchall())}

    @app.post("/api/playbook/rules/{rule_id}/approve")
    async def approve(rule_id: int):
        if conn.execute("SELECT 1 FROM playbook_rules WHERE id=?", (rule_id,)).fetchone() is None:
            raise HTTPException(404, "Regra não encontrada.")
        approve_rule(conn, rule_id)
        pb = current_playbook(conn)
        return {"ok": True, "playbook_approved": bool(pb and pb.approved)}

    @app.get("/api/costs")
    async def costs():
        now = datetime.now(UTC)
        start = now.astimezone(ZoneInfo(tz)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        lo = start.astimezone(UTC).isoformat(timespec="seconds")
        rows = lambda col: [dict(r) for r in conn.execute(  # noqa: E731
            f"SELECT {col}, SUM(usd) AS usd FROM api_costs WHERE one_time=0 AND ts_utc >= ? GROUP BY {col} "
            "ORDER BY usd DESC", (lo,))]
        return {"spent_month_usd": month_spent(conn, now, tz), "budget_usd": ctx.settings.budget_usd,
                "budget_state": budget_state(conn, ctx.settings, now),
                "one_time_usd": conn.execute("SELECT COALESCE(SUM(usd), 0) FROM api_costs WHERE one_time=1").fetchone()[0],
                "by_purpose": rows("purpose"), "by_model": rows("model")}

    @app.post("/api/cost-overrides")
    async def cost_override(body: CostOverride):
        conn.execute("INSERT OR REPLACE INTO cost_overrides VALUES (?,?,?,?,?)",
                     (body.symbol, body.avg_cost_usd, body.qty, body.note, datetime.now(UTC).isoformat(timespec="seconds")))
        conn.commit()
        return {"ok": True, **body.model_dump()}

    @app.post("/api/csv/{exchange}")
    async def upload_csv(exchange: Literal["binance", "mexc", "bybit", "gate"], request: Request):
        """Corpo cru do CSV (sem multipart). Limite de 5 MB."""
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        body = bytearray()
        if declared <= MAX_CSV:
            async for chunk in request.stream():
                body += chunk
                if len(body) > MAX_CSV:
                    break
        if declared > MAX_CSV or len(body) > MAX_CSV:
            raise HTTPException(413, "Arquivo acima de 5 MB.")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            path.write_bytes(body)
            try:
                trades = parse_csv(exchange, path, ctx.settings.symbol_aliases)
            except (KeyError, ValueError, UnicodeDecodeError, csv.Error) as e:
                raise HTTPException(422, f"CSV fora do formato de {exchange}: {type(e).__name__}") from e
        imported = insert_trades(conn, trades)
        conn.commit()
        return {"imported": imported, "read": len(trades)}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        ctx.hub.add(websocket)  # antes do accept: o hub só envia depois que o estado vira CONNECTED
        try:
            await websocket.accept()
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            ctx.hub.discard(websocket)

    index = static_dir / "index.html"

    @app.get("/{path:path}")
    async def front(path: str):
        if path.startswith(("api/", "ws")) or path == "api":
            raise HTTPException(404)
        if not index.is_file():
            return PlainTextResponse(NO_FRONT)
        target = (static_dir / path).resolve()
        return FileResponse(target if target.is_file() and target.is_relative_to(static_dir.resolve()) else index)

    return app
