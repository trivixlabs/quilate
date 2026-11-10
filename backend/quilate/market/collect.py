import json
import logging
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date

from quilate.market import sources as S

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)  # em INFO ele imprime a URL, que pode trazer a chave da FRED
_SECRET_RE = re.compile(r"(api_key=|x-cg-demo-api-key['\":= ]+)[^&\s'\"]+", re.I)
STABLES = frozenset({"USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDE", "USDS", "PYUSD", "USD1", "USDD", "BUSD", "USDG"})
DXY_SERIES = "DTWEXBGS"  # índice amplo do dólar (FRED); o DXY ICE não é público
USDBRL_SERIES = "DEXBZUS"  # reais por 1 dólar (FRED), usado no total em BRL da tela
CG_PAUSE = 0.7  # CoinGecko: até 90 chamadas por minuto
CANDLE_DAYS = 400


@dataclass
class CollectReport:
    ok: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def alt_season_index(alt_90d: list[float], btc_90d: float) -> int:
    """Percentual de altcoins com retorno de 90 dias acima do BTC."""
    return round(100 * sum(r > btc_90d for r in alt_90d) / len(alt_90d))


def _ret(prices: list[float]) -> float:
    return prices[-1] / prices[0] - 1


def _save(conn: sqlite3.Connection, day: date, key: str, value) -> None:
    conn.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)",
                 (day.isoformat(), key, json.dumps(value, default=asdict)))
    conn.commit()


async def _candles(conn, clients, symbols: list[str], rep: CollectReport) -> None:
    ordered = sorted(clients.values(), key=lambda c: c.name != "binance")  # Binance primeiro
    for c in ordered:
        try:
            bases = S.usdt_bases(await c.ex.load_markets())
            for s in (s for s in symbols if s in bases):
                try:
                    rows = await c.fetch_daily_candles(s, "USDT", CANDLE_DAYS)
                except Exception as e:  # um símbolo ruim não derruba a corretora
                    rep.failed[f"candles:{c.name}:{s}"] = _mask(f"{type(e).__name__}: {e}")
                    continue
                conn.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?)",
                                 [(c.name, s, "USDT", r.day.isoformat(), r.open, r.high, r.low, r.close, r.volume_quote)
                                  for r in rows])
        except Exception as e:
            rep.failed[f"candles:{c.name}"] = _mask(f"{type(e).__name__}: {e}")
        conn.commit()
    if not any(k.startswith("candles:") for k in rep.failed):
        rep.ok.append("candles")


def _mask(text: str) -> str:
    return _SECRET_RE.sub(r"\1***", text)


async def collect_daily(conn, http, clients, settings, day: date) -> CollectReport:
    rep = CollectReport()
    state: dict = {}

    async def run(name: str, fn) -> None:
        try:
            await fn()
            rep.ok.append(name)
        except Exception as e:  # uma fonte fora do ar não derruba as outras
            log.warning("coleta %s falhou: %s", name, _mask(str(e)))
            rep.failed[name] = _mask(f"{type(e).__name__}: {e}")

    def held() -> list[str]:
        syms = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM positions WHERE qty > 0")}
        return sorted((syms | {"BTC"}) - STABLES)

    async def cg_assets():
        state["assets"] = await S.coingecko_assets(http)
        _save(conn, day, "cg_assets", {k: {"coingecko_id": a.coingecko_id, "name": a.name, "rank": a.rank}
                                       for k, a in state["assets"].items()})

    def known() -> dict[str, S.AssetInfo]:
        if "assets" not in state:
            raise RuntimeError("cg_assets indisponível")
        return state["assets"]

    async def cg_markets():
        ids = [known()[s].coingecko_id for s in held() if s in known()]
        _save(conn, day, "cg_markets", await S.coingecko_markets(http, ids))

    async def cg_global():
        _save(conn, day, "cg_global", await S.coingecko_global(http))

    async def fng():
        _save(conn, day, "fng", await S.fear_greed(http))

    async def derivs():
        _save(conn, day, "derivs", await S.coinalyze_derivs(http, held()))

    async def bgeometrics():
        if conn.execute("SELECT 1 FROM snapshots WHERE day=? AND key='btc_onchain'", (day.isoformat(),)).fetchone():
            return  # no máximo uma coleta por dia
        _save(conn, day, "btc_onchain", await S.bgeometrics_btc(http))

    async def dxy():
        _save(conn, day, "dxy", await S.fred_latest(http, DXY_SERIES))

    async def usdbrl():
        _save(conn, day, "usdbrl", await S.fred_latest(http, USDBRL_SERIES))

    async def etf_flows():
        _save(conn, day, "etf_flows", await S.tftc_etf_flows(http))

    async def stablecoins():
        _save(conn, day, "stablecoins", await S.defillama_stablecoins(http))

    async def alt_season():
        top = [a for a in sorted(known().values(), key=lambda a: a.rank)[:50]
               if a.symbol not in STABLES and a.symbol != "BTC"]
        rets = []
        for a in [known()["BTC"], *top]:
            try:
                rets.append(_ret((await S.coingecko_chart(http, a.coingecko_id, 90)).prices))
            except Exception as e:  # ativo sem gráfico fica de fora do índice
                if a.symbol == "BTC":
                    raise
                log.warning("alt_season: %s ignorado (%s)", a.symbol, _mask(str(e)))
            await S._pause(CG_PAUSE)
        _save(conn, day, "alt_season", alt_season_index(rets[1:], rets[0]))

    async def delisting():
        _save(conn, day, "delisting", await S.delisting_flags(http, clients, held()))

    async def inflation():
        out = {}
        for s in held():
            if s not in known():
                continue
            try:
                ch = await S.coingecko_chart(http, known()[s].coingecko_id, 365)
            except Exception as e:
                log.warning("inflation: %s ignorado (%s)", s, _mask(str(e)))
                continue
            finally:
                await S._pause(CG_PAUSE)
            supply = [m / p for m, p in zip(ch.market_caps, ch.prices, strict=False) if p]
            if not supply or not supply[0]:
                continue
            # ponytail: oferta = market_cap / preço; desbloqueio de 90 dias sem fonte grátis confirmada (spec 14)
            out[s] = {"inflation_12m": supply[-1] / supply[0] - 1, "unlock_90d": None}
        _save(conn, day, "inflation", out)

    for name, fn in [("cg_assets", cg_assets), ("cg_markets", cg_markets), ("cg_global", cg_global),
                     ("fng", fng), ("derivs", derivs), ("bgeometrics", bgeometrics), ("dxy", dxy),
                     ("usdbrl", usdbrl), ("etf_flows", etf_flows), ("stablecoins", stablecoins), ("alt_season", alt_season),
                     ("delisting", delisting), ("inflation", inflation)]:
        await run(name, fn)
    await _candles(conn, clients, held(), rep)
    return rep
