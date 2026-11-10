import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import anyio
import pytest
import sqlite_vec
from fastapi.testclient import TestClient

from quilate.ai.claude import Claude  # noqa: F401  (só para falhar cedo se o módulo sumir)
from quilate.api.app import create_app
from quilate.api.hub import Hub
from quilate.config import load_settings
from quilate.context import AppContext
from quilate.db import migrate
from quilate.exchanges.live import PriceBook, Tick
from quilate.telegram.bot import DISCLAIMER

BASE = "http://127.0.0.1:8000"


def local(app):
    # o host vai no cabeçalho do cliente porque o TestClient fixa "testserver" nas conexões WebSocket
    return TestClient(app, base_url=BASE, headers={"host": "127.0.0.1:8000"})
TODAY = datetime.now(ZoneInfo("America/Sao_Paulo")).date()


@pytest.fixture
def ctx(tmp_path):
    # o TestClient roda o app em outra thread: a conexão do teste precisa permitir isso
    conn = sqlite3.connect(tmp_path / "t.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    migrate(conn)
    yield AppContext(replace(load_settings(), trigger_topic=101, group_topics={101: "MARKET UPDATES", 102: "GENERAL"}, analyst_username="usuario_do_analista",
                             analyst_name=""), conn, {}, PriceBook(), None, None, None, None, Hub())
    conn.close()


@pytest.fixture
def client(ctx, tmp_path):
    return local(create_app(ctx, static_dir=tmp_path / "sem-front"))


def verdict(ctx, symbol, final, day=None, cons=(), pros=(), created="2026-01-01T10:00:00+00:00", price=2.0):
    ctx.conn.execute(
        "INSERT INTO verdicts (day, symbol, trigger, rubric_verdict, ai_verdict, final_verdict, confidence,"
        " signals_json, pros_json, cons_json, main_risk, cited_json, no_analyst, flag, price_usd, price_btc,"
        " created_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ((day or TODAY).isoformat(), symbol, "diario", final, None, final, None,
         json.dumps([{"code": "S1", "name": "Tendência", "alert": True, "value": "-30"}]),
         json.dumps(list(pros)), json.dumps(list(cons)), "risco", "[]", 0, None, price, 1.0, created))
    ctx.conn.commit()


def position(ctx, symbol, qty, exchange="binance", wallet="spot", stale=0):
    ctx.conn.execute("INSERT INTO positions VALUES (?,?,?,?,?,?)",
                     (exchange, symbol, wallet, qty, "2026-01-01T00:00:00+00:00", stale))
    ctx.conn.commit()


def candles(ctx, symbol, closes):
    """closes[-1] é o dia de hoje."""
    for i, c in enumerate(closes):
        d = (TODAY - timedelta(days=len(closes) - 1 - i)).isoformat()
        ctx.conn.execute("INSERT INTO candles VALUES ('binance',?, 'USDT',?,?,?,?,?,?)", (symbol, d, c, c, c, c, 1))
    ctx.conn.commit()


def buy(ctx, symbol, qty, price, tid="t1"):
    ctx.conn.execute("INSERT INTO trades VALUES ('binance',?,?,'buy',?,?,0,'2025-01-01T00:00:00+00:00','api')",
                     (tid, symbol, qty, price))
    ctx.conn.commit()


@pytest.fixture
def seeded(ctx):
    position(ctx, "BTC", 1.0)
    position(ctx, "ETH", 10.0, exchange="mexc")
    position(ctx, "PEPE", 1000.0, stale=1)
    for s, closes in {"BTC": [100.0, 110.0], "ETH": [10.0, 12.0], "PEPE": [1.0, 1.0]}.items():
        candles(ctx, s, closes)
    buy(ctx, "BTC", 1.0, 50.0, "t1")
    buy(ctx, "ETH", 10.0, 20.0, "t2")
    verdict(ctx, "BTC", "Manter", pros=["forte", "outro"])
    verdict(ctx, "ETH", "Reduzir", cons=["fraco"], pros=["x"])
    verdict(ctx, "PEPE", "Sair", cons=["morto"])
    return ctx


@pytest.fixture
def seeded_unknown_cost(seeded):
    return seeded  # PEPE não tem trade nenhum: custo desconhecido


def test_foreign_host_header_is_rejected(client):
    assert client.get("/api/overview", headers={"host": "evil.com"}).status_code == 403
    assert client.get("/api/overview", headers={"host": "localhost:9999"}).status_code == 403
    assert client.get("/api/overview", headers={"host": "localhost:8000"}).status_code == 200


def test_overview_shape(client):
    body = client.get("/api/overview").json()
    assert body["disclaimer"] == DISCLAIMER == "Material de apoio à decisão, não é recomendação de investimento."
    assert set(body) >= {"total_usd", "total_brl", "invested_usd", "pnl_usd", "pnl_pct", "by_exchange", "history",
                         "spent_month_usd", "budget_usd", "budget_state", "last_cycle_utc", "playbook_approved"}
    assert body["budget_state"] == "ok" and body["playbook_approved"] is False and body["total_brl"] is None


def test_overview_numbers(seeded):
    c = local(create_app(seeded))
    body = c.get("/api/overview").json()
    # BTC 110, ETH 12*10=120, PEPE 1000*1=1000 (sem ticks: último fechamento)
    assert body["total_usd"] == pytest.approx(1230.0)
    assert body["invested_usd"] == pytest.approx(250.0)       # só moedas com custo conhecido
    assert body["pnl_usd"] == pytest.approx(-20.0)  # BTC +60, ETH -80
    assert body["pnl_pct"] == pytest.approx(-20 / 250)
    ex = {e["exchange"]: e for e in body["by_exchange"]}
    assert ex["binance"]["usd"] == pytest.approx(1110.0) and ex["binance"]["stale"] is True
    assert ex["mexc"]["share"] == pytest.approx(120 / 1230) and ex["mexc"]["stale"] is False
    assert body["history"][-1]["usd"] == pytest.approx(1230.0)
    assert body["last_cycle_utc"] == "2026-01-01T10:00:00+00:00"


def test_total_brl_uses_snapshot_rate_only(seeded):
    c = local(create_app(seeded))
    seeded.conn.execute("INSERT INTO snapshots VALUES (?,?,?)", (TODAY.isoformat(), "usdbrl", "5.0"))
    seeded.conn.commit()
    assert c.get("/api/overview").json()["total_brl"] == pytest.approx(1230.0 * 5)


def test_live_price_wins_over_candle(seeded):
    seeded.book.update(Tick("binance", "BTC", 200.0, 1))
    c = local(create_app(seeded))
    assert c.get("/api/overview").json()["total_usd"] == pytest.approx(200 + 120 + 1000)


def test_groups_order(client, seeded):
    body = client.get("/api/verdicts").json()
    assert list(body["groups"]) == ["Sair", "Reduzir", "Manter"]
    assert body["day"] == TODAY.isoformat()
    assert [c["symbol"] for c in body["groups"]["Sair"]] == ["PEPE"]


def test_latest_verdict_of_the_day_wins(seeded):
    verdict(seeded, "BTC", "Sair", cons=["novo"], created="2026-01-01T12:00:00+00:00")
    c = local(create_app(seeded))
    groups = c.get(f"/api/verdicts?day={TODAY.isoformat()}").json()["groups"]
    assert [x["symbol"] for x in groups["Sair"]] == ["PEPE", "BTC"]  # ordem por valor
    assert [x["symbol"] for x in groups["Manter"]] == []


def test_card_fields_and_reason(seeded):
    c = local(create_app(seeded))
    g = c.get("/api/verdicts").json()["groups"]
    eth = g["Reduzir"][0]
    assert eth["reason"] == "fraco" and eth["exchanges"] == ["mexc"]
    assert eth["value_usd"] == pytest.approx(120.0) and eth["pnl_usd"] == pytest.approx(-80.0)
    assert eth["change_24h"] == pytest.approx(0.2) and eth["cost_unknown"] is False
    assert eth["signals"] == [{"code": "S1", "name": "Tendência", "alert": True, "value": "-30"}]
    assert eth["alerts"] == 1 and eth["ai_verdict"] is None and eth["no_analyst"] is False
    assert g["Manter"][0]["reason"] == "forte"  # Manter usa o primeiro pró


def test_unknown_cost_card(client, seeded_unknown_cost):
    card = client.get("/api/coins/PEPE").json()
    assert card["cost_unknown"] is True and card["avg_cost_usd"] is None and card["pnl_usd"] is None


def test_coin_detail(seeded):
    seeded.conn.execute("INSERT INTO messages (msg_id, topic_id, is_analyst, date_utc, text, media_kind)"
                        " VALUES (1, 101, 1, '2026-01-02T00:00:00+00:00', 'BTC forte', NULL)")
    seeded.conn.execute("INSERT INTO messages (msg_id, topic_id, is_analyst, date_utc, text, media_kind)"
                        " VALUES (2, 102, 1, '2026-01-03T00:00:00+00:00', NULL, 'audio')")
    seeded.conn.execute("INSERT INTO chunks (id, source_kind, source_id, text, t_start, date_utc)"
                        " VALUES (7, 'transcricao', 'v1', 'trecho falado', 61.5, '2026-01-03T00:00:00+00:00')")
    for msg, chunk, d in [(1, None, "2026-01-02"), (2, 7, "2026-01-03")]:
        seeded.conn.execute("INSERT INTO mentions (msg_id, chunk_id, symbol, is_analyst, date_utc)"
                            " VALUES (?,?, 'BTC', 1, ?)", (msg, chunk, d))
    seeded.conn.execute("INSERT INTO mentions (msg_id, symbol, is_analyst, date_utc) VALUES (1, 'BTC', 0, '2026-01-05')")
    seeded.conn.commit()
    card = local(create_app(seeded)).get("/api/coins/BTC").json()
    assert card["avg_cost_usd"] == pytest.approx(50.0) and card["qty"] == 1.0
    assert card["by_exchange"] == [{"exchange": "binance", "wallet": "spot", "qty": 1.0}]
    assert card["candles"][-1] == {"day": TODAY.isoformat(), "close": 110.0}
    assert card["pros"] == ["forte", "outro"] and card["main_risk"] == "risco"
    q = card["quotes"]
    assert [x["kind"] for x in q] == ["transcricao", "texto"]  # mais novo primeiro; só falas do analista
    assert q[0]["t_start"] == 61.5 and q[0]["text"] == "trecho falado" and q[0]["topic"] == "GENERAL"
    assert q[1]["topic"] == "MARKET UPDATES" and q[1]["t_start"] is None


def test_coin_not_found(client):
    assert client.get("/api/coins/ZZZ").status_code == 404
    assert client.get("/api/coins/b'tc").status_code in (404, 422)


def test_market_has_source_and_day(client, ctx):
    ctx.conn.execute("INSERT INTO snapshots VALUES ('2026-01-01','fng',?)", (json.dumps({"value": 40}),))
    ctx.conn.execute("INSERT INTO snapshots VALUES ('2026-01-03','fng',?)", (json.dumps({"value": 55}),))
    ctx.conn.commit()
    body = client.get("/api/market").json()
    assert body["fng"]["day"] == "2026-01-03" and body["fng"]["value"] == {"value": 55} and body["fng"]["source"]
    assert body["dxy"] is None
    assert set(body) == {"fng", "cg_global", "alt_season", "btc_onchain", "derivs", "dxy", "etf_flows", "stablecoins"}


def test_market_dominance_has_7d_change(client, ctx):
    for i in range(7):
        d = (TODAY - timedelta(days=6 - i)).isoformat()
        ctx.conn.execute("INSERT INTO snapshots VALUES (?,'cg_global',?)", (d, json.dumps({"btc_dominance": 55.0 + i * 0.5})))
    ctx.conn.commit()
    g = client.get("/api/market").json()["cg_global"]
    assert g["value"] == {"btc_dominance": 58.0} and g["change_7d"] == pytest.approx(3.0)


def test_market_dominance_without_7_days_has_no_change(client, ctx):
    ctx.conn.execute("INSERT INTO snapshots VALUES (?,'cg_global',?)", (TODAY.isoformat(), json.dumps({"btc_dominance": 55.0})))
    ctx.conn.commit()
    assert client.get("/api/market").json()["cg_global"]["change_7d"] is None


def test_portfolio_and_costs_and_track(seeded):
    c = local(create_app(seeded))
    p = c.get("/api/portfolio").json()
    assert {x["symbol"] for x in p["coins"]} == {"BTC", "ETH", "PEPE"}
    seeded.conn.execute("INSERT INTO api_costs (ts_utc, model, purpose, usd) VALUES (?,?,?,?)",
                        (datetime.now(UTC).isoformat(), "claude-sonnet-5-5", "veredito", 1.5))
    seeded.conn.commit()
    costs = c.get("/api/costs").json()
    assert costs["spent_month_usd"] == pytest.approx(1.5) and costs["by_purpose"] == [{"purpose": "veredito", "usd": 1.5}]
    assert set(c.get("/api/track").json()) == {"by_verdict", "by_signal", "verdicts"}


def test_track_lists_verdicts_with_result(ctx, client):
    candles(ctx, "BTC", [100.0 + i for i in range(11)])  # hoje é o último
    verdict(ctx, "BTC", "Manter", day=TODAY - timedelta(days=10), price=100.0)
    verdict(ctx, "BTC", "Manter", day=TODAY - timedelta(days=2), price=108.0)  # ainda sem 7 dias
    body = client.get("/api/track").json()
    assert "Manter" not in body["by_verdict"]  # Manter do BTC fica fora da taxa (acertaria sempre)
    [v] = body["verdicts"]
    assert v["day"] == (TODAY - timedelta(days=10)).isoformat() and v["symbol"] == "BTC" and v["verdict"] == "Manter"
    assert set(v["outcomes"]) == {"7"}
    r = v["outcomes"]["7"]
    assert r["hit"] is True and r["r_hold"] == pytest.approx(0.07) and r["r_btc"] == pytest.approx(0.07)
    assert r["r_paper"] == pytest.approx(0.07)


def test_playbook_and_approve(ctx, client):
    assert client.get("/api/playbook").json()["version_id"] is None
    ctx.conn.execute("INSERT INTO playbook_versions (id, created_utc, markdown) VALUES (1,'2026-01-01','# m')")
    ctx.conn.execute("INSERT INTO playbook_rules (id, version_id, category, text) VALUES (5,1,'saida','vender')")
    ctx.conn.commit()
    pb = client.get("/api/playbook").json()
    assert pb["approved"] is False and pb["rules"][0]["id"] == 5 and pb["rules"][0]["approved"] is False
    assert client.post("/api/playbook/rules/99/approve").status_code == 404
    assert client.post("/api/playbook/rules/5/approve").status_code == 200
    assert client.get("/api/playbook").json()["approved"] is True
    # o rascunho semanal aparece para aprovação mesmo com a v1 aprovada
    ctx.conn.execute("INSERT INTO playbook_versions (id, created_utc, markdown, parent_id) VALUES (2,'2026-01-08','# v2',1)")
    pb = client.get("/api/playbook").json()
    assert (pb["version_id"], pb["approved"]) == (2, False)
    assert client.get("/api/overview").json()["playbook_approved"] is True


def test_playbook_sources_timeline_and_lives(ctx, client):
    pb = client.get("/api/playbook").json()
    assert pb["sources"] == {} and pb["timeline"] == [] and pb["lives"] == [] and pb["lives_count"] == {}
    msg = "INSERT INTO messages (msg_id, topic_id, is_analyst, date_utc, text, media_kind) VALUES (?,?,?,?,?,?)"
    ctx.conn.execute(msg, (10, 101, 1, "2026-11-03T11:00:00+00:00", "BTC segura o suporte.", None))
    ctx.conn.execute(msg, (11, 101, 1, "2026-11-04T11:00:00+00:00", "Dominância subindo.", "foto"))
    ctx.conn.execute(msg, (12, 101, 0, "2026-11-04T12:00:00+00:00", "aluno perguntando", None))
    ctx.conn.execute(msg, (13, 102, 1, "2026-11-04T13:00:00+00:00", "outro tópico", None))
    ctx.conn.execute("INSERT INTO chunks (id, source_kind, source_id, text, t_start, date_utc) VALUES "
                     "(7,'transcricao','https://www.youtube.com/watch?v=abc','Realizo 25% perto da máxima.',125.0,"
                     "'2026-10-01T23:00:00+00:00')")
    ctx.conn.execute("INSERT INTO media_jobs (kind, ref, msg_id, status) VALUES "
                     "('youtube','https://www.youtube.com/watch?v=abc',10,'transcrito'),"
                     "('youtube','https://youtu.be/xyz',11,'erro'),('audio','/tmp/a.ogg',11,'pendente')")
    ctx.conn.execute("INSERT INTO playbook_versions (id, created_utc, markdown) VALUES (1,'2026-01-01','# m')")
    ctx.conn.execute("INSERT INTO playbook_rules (id, version_id, category, text, source_ids_json) VALUES "
                     "(5,1,'saida','vender','[\"m:13\", \"c:7\", \"m:999\"]')")
    ctx.conn.commit()
    pb = client.get("/api/playbook").json()
    assert pb["sources"]["m:13"] == {"date_utc": "2026-11-04T13:00:00+00:00", "topic": "GENERAL",
                                     "kind": "texto", "text": "outro tópico", "url": None, "t_start": None}
    assert pb["sources"]["c:7"]["url"] == "https://www.youtube.com/watch?v=abc&t=125s"
    assert pb["sources"]["c:7"]["kind"] == "transcricao" and pb["sources"]["c:7"]["t_start"] == 125.0
    assert "m:999" not in pb["sources"]  # fonte apagada não quebra a resposta
    assert [t["id"] for t in pb["timeline"]] == ["m:11", "m:10"]
    assert pb["timeline"][0] == {"id": "m:11", "date_utc": "2026-11-04T11:00:00+00:00", "text": "Dominância subindo.",
                                 "kind": "foto"}
    assert {(x["url"], x["status"]) for x in pb["lives"]} == {
        ("https://www.youtube.com/watch?v=abc", "transcrito"), ("https://youtu.be/xyz", "erro")}
    assert pb["lives"][0]["date_utc"] == "2026-11-04T11:00:00+00:00"  # mais nova primeiro
    assert pb["lives_count"] == {"transcrito": 1, "erro": 1}  # o áudio não é live


@pytest.mark.parametrize("body", [
    {"symbol": "btc", "avg_cost_usd": 1, "qty": None, "note": ""},
    {"symbol": "BTC", "avg_cost_usd": 0, "qty": None, "note": ""},
    {"symbol": "BTC", "avg_cost_usd": -3, "qty": None, "note": ""},
    {"symbol": "A" * 16, "avg_cost_usd": 1, "qty": None, "note": ""},
    {"symbol": "BTC;--", "avg_cost_usd": 1, "qty": None, "note": ""},
])
def test_cost_override_validation(client, ctx, body):
    assert client.post("/api/cost-overrides", json=body).status_code == 422
    assert ctx.conn.execute("SELECT COUNT(*) FROM cost_overrides").fetchone()[0] == 0


def test_cost_override_fixes_unknown_cost(seeded):
    c = local(create_app(seeded))
    r = c.post("/api/cost-overrides", json={"symbol": "PEPE", "avg_cost_usd": 0.5, "qty": None, "note": "doação"})
    assert r.status_code == 200
    card = c.get("/api/coins/PEPE").json()
    assert card["cost_unknown"] is False and card["avg_cost_usd"] == 0.5 and card["pnl_usd"] == pytest.approx(500.0)


BINANCE_CSV = (
    "Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n"
    "2025-03-01 10:00:00,BTCUSDT,BUY,50000,0.1BTC,5000USDT,0.0001BTC\n"
)


def test_csv_upload(ctx, client):
    r = client.post("/api/csv/binance", content=BINANCE_CSV.encode(), headers={"content-type": "text/csv"})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    assert ctx.conn.execute("SELECT COUNT(*) FROM trades WHERE source='csv'").fetchone()[0] == 1
    assert client.post("/api/csv/binance", content=BINANCE_CSV.encode()).json()["imported"] == 0  # repetido


def test_csv_skips_trade_already_synced_from_api(ctx, client):
    # a API grava com milissegundos e id da corretora; o CSV da Binance traz o segundo e não tem id
    ctx.conn.execute("INSERT INTO trades VALUES ('binance','123','BTC','buy',0.1,50000,5,"
                     "'2025-03-01T10:00:00.250000+00:00','api')")
    r = client.post("/api/csv/binance", content=BINANCE_CSV.encode())
    assert r.json() == {"imported": 0, "read": 1}
    assert ctx.conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1


def test_csv_rejects_unknown_exchange_big_and_garbage(client):
    assert client.post("/api/csv/kraken", content=b"x").status_code in (404, 422)
    assert client.post("/api/csv/binance", content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert client.post("/api/csv/binance", content=b"lixo,sem\ncolunas,certas\n").status_code == 422


def test_ws_receives_tick(client, ctx):
    with client.websocket_connect("/ws") as ws:
        anyio.run(ctx.hub.broadcast, {"type": "tick", "symbol": "BTC", "price_usd": 1, "ts": 0})
        assert ws.receive_json()["symbol"] == "BTC"


def test_ws_foreign_origin_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect
    for origin in ("http://evil.com", "http://127.0.0.1:9999"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": origin}):
                pass
    for origin in ("http://127.0.0.1:8000", "http://localhost:8000", "http://localhost:5173"):
        with client.websocket_connect("/ws", headers={"origin": origin}):
            pass


def test_ws_foreign_host_is_rejected(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"host": "evil.com"}):
            pass


class FakeWS:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send_json(self, event):
        if self.fail:
            raise RuntimeError("socket morto")
        self.sent.append(event)


async def test_hub_throttles_ticks_per_symbol_and_drops_dead_sockets():
    clock = [0.0]
    hub, ok, dead = Hub(now=lambda: clock[0]), FakeWS(), FakeWS(fail=True)
    hub.add(ok)
    hub.add(dead)
    tick = lambda s, t: {"type": "tick", "symbol": s, "price_usd": 1, "ts": t}  # noqa: E731
    for t in (0.0, 0.1, 0.3, 0.4, 0.6):
        clock[0] = t
        await hub.broadcast(tick("BTC", t))
    await hub.broadcast(tick("ETH", 0))
    await hub.broadcast({"type": "verdict", "symbol": "BTC"})
    await hub.broadcast({"type": "verdict", "symbol": "BTC"})
    assert [e["ts"] for e in ok.sent if e["type"] == "tick" and e["symbol"] == "BTC"] == [0.0, 0.6]
    assert len([e for e in ok.sent if e["type"] == "verdict"]) == 2  # só tick tem limite
    assert dead not in hub.sockets


async def test_hub_flushes_trailing_tick_when_window_closes():
    clock, delays, wake = [0.0], [], asyncio.Event()

    async def sleep(d):
        delays.append(d)
        await wake.wait()

    hub, ws = Hub(now=lambda: clock[0], sleep=sleep), FakeWS()
    hub.add(ws)
    for t in (0.0, 0.1, 0.3):
        clock[0] = t
        await hub.broadcast({"type": "tick", "symbol": "BTC", "price_usd": t, "ts": t})
    await asyncio.sleep(0)  # o timer começa
    assert [e["ts"] for e in ws.sent] == [0.0]
    assert delays == [pytest.approx(0.4)]  # um timer só, até fechar a janela aberta em 0.0
    clock[0] = 0.5
    wake.set()
    for _ in range(3):
        await asyncio.sleep(0)
    assert [e["ts"] for e in ws.sent] == [0.0, 0.3]  # o último preço da rajada chega à tela


async def test_hub_direct_tick_cancels_stale_timer():
    clock, delays = [0.0], []

    async def sleep(d):
        delays.append(d)
        await asyncio.Event().wait()  # nunca acorda sozinho

    hub, ws = Hub(now=lambda: clock[0], sleep=sleep), FakeWS()
    hub.add(ws)
    for t in (0.0, 0.1, 0.6, 0.7):  # 0.1 segurado, 0.6 passa direto, 0.7 abre uma janela nova
        clock[0] = t
        await hub.broadcast({"type": "tick", "symbol": "BTC", "price_usd": t, "ts": t})
        await asyncio.sleep(0)
    assert [e["ts"] for e in ws.sent] == [0.0, 0.6]
    assert delays == [pytest.approx(0.4), pytest.approx(0.4)]  # timer novo para a janela de 0.6, não o velho


def test_no_front_message_and_spa_fallback(ctx, tmp_path):
    c = local(create_app(ctx, static_dir=tmp_path / "nada"))
    r = c.get("/")
    assert r.status_code == 200 and "front" in r.text.lower() and "construído" in r.text
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>app</html>")
    (static / "assets" / "a.js").write_text("js")
    c = local(create_app(ctx, static_dir=static))
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/moedas/BTC").text == "<html>app</html>"
    assert c.get("/assets/a.js").text == "js"
    assert c.get("/api/nao-existe").status_code == 404
    assert "root:" not in c.get("/..%2f..%2f..%2f..%2fetc/passwd").text


def test_no_cors_headers(client):
    r = client.get("/api/overview", headers={"origin": "http://evil.com"})
    assert "access-control-allow-origin" not in r.headers


def test_post_from_foreign_origin_is_rejected(client):
    assert client.post("/api/playbook/rules/1/approve", headers={"origin": "http://evil.com"}).status_code == 403
    assert client.post("/api/playbook/rules/1/approve", headers={"origin": "http://localhost:5173"}).status_code == 404


def test_portfolio_flags_exchanges_without_permission_check(client, seeded):
    coins = {c["symbol"]: c for c in client.get("/api/portfolio").json()["coins"]}
    assert coins["ETH"]["positions"][0]["permissions_verified"] is False  # mexc: a API não expõe permissões
    assert coins["BTC"]["positions"][0]["permissions_verified"] is True


def test_other_port_builds_its_own_allowlist(ctx, tmp_path):
    app = create_app(ctx, static_dir=tmp_path / "sem-front", port=8123)
    c = TestClient(app, base_url="http://127.0.0.1:8123", headers={"host": "127.0.0.1:8123"})
    assert c.get("/api/overview").status_code == 200
    assert c.get("/api/overview", headers={"host": "localhost:8123"}).status_code == 200
    assert c.get("/api/overview", headers={"host": "127.0.0.1:8000"}).status_code == 403
    assert c.post("/api/playbook/rules/1/approve", headers={"origin": "http://127.0.0.1:8123"}).status_code == 404
    assert c.post("/api/playbook/rules/1/approve", headers={"origin": "http://localhost:5173"}).status_code == 404  # dev
    assert c.post("/api/playbook/rules/1/approve", headers={"origin": "http://127.0.0.1:8000"}).status_code == 403


def test_overview_and_playbook_expose_analyst_name_and_trigger_topic_name(ctx, client):
    ctx.settings = replace(ctx.settings, analyst_name="Ana", trigger_topic=7, group_topics={7: "DIÁRIO"})
    assert client.get("/api/overview").json()["analyst_name"] == "Ana"
    assert client.get("/api/playbook").json()["trigger_topic_name"] == "DIÁRIO"
    ctx.conn.execute("INSERT INTO messages (msg_id, topic_id, is_analyst, date_utc, text) "
                     "VALUES (1, 0, 1, '2026-11-04T11:00:00+00:00', 'sem tópico')")
    ctx.conn.commit()
    ctx.settings = replace(ctx.settings, trigger_topic=0)
    assert client.get("/api/playbook").json()["trigger_topic_name"] is None
    assert client.get("/api/playbook").json()["timeline"] == []
