"""Uma função por fonte de dados de mercado. Cada uma devolve dados já normalizados."""
import asyncio
import time
from dataclasses import dataclass

import httpx

from quilate.secrets import get_secret, require_secret

CG = "https://api.coingecko.com/api/v3"
COINALYZE = "https://api.coinalyze.net/v1"
BGEOMETRICS = "https://bitcoin-data.com/v1"
FRED = "https://api.stlouisfed.org/fred/series/observations"
DEFILLAMA = "https://stablecoins.llama.fi/stablecoins"
FNG = "https://api.alternative.me/fng/"
# Lista de produtos do site da Binance: cada símbolo traz `tags`, e "Monitoring" é a Monitoring Tag.
BINANCE_PRODUCTS_URL = "https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products"
# URL NÃO verificada: o JSON do TFTC não foi localizado (a página do tracker não expõe um endpoint).
TFTC_URL = "https://tftc.io/data/etf-flows.json"


@dataclass(frozen=True)
class AssetInfo:
    coingecko_id: str
    symbol: str
    name: str
    rank: int


@dataclass(frozen=True)
class Market:
    price: float
    market_cap: float
    volume_24h: float
    ath: float
    circulating_supply: float


@dataclass(frozen=True)
class Chart:
    prices: list[float]
    market_caps: list[float]


@dataclass(frozen=True)
class Derivs:
    funding: float
    open_interest: float
    liquidations_24h: float


@dataclass(frozen=True)
class DelistInfo:
    monitoring_tag: bool | None
    listed_on: int


async def _pause(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _get(http: httpx.AsyncClient, url: str, headers: dict | None = None, **params):
    r = await http.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


async def _cg(http, path: str, **params):
    key = get_secret("coingecko_key")
    return await _get(http, f"{CG}/{path}", {"x-cg-demo-api-key": key} if key else None, **params)


async def coingecko_assets(http) -> dict[str, AssetInfo]:
    rows = await _cg(http, "coins/markets", vs_currency="usd", order="market_cap_desc", per_page=250, page=1)
    out: dict[str, AssetInfo] = {}
    for r in rows:  # símbolo repetido: vale o de maior ranking (vem primeiro)
        sym = r["symbol"].upper()
        out.setdefault(sym, AssetInfo(r["id"], sym, r["name"], r["market_cap_rank"]))
    return out


async def coingecko_markets(http, ids: list[str]) -> dict[str, Market]:
    rows = await _cg(http, "coins/markets", vs_currency="usd", ids=",".join(ids), per_page=250)
    return {r["id"]: Market(r["current_price"], r["market_cap"], r["total_volume"], r["ath"], r["circulating_supply"])
            for r in rows}


async def coingecko_chart(http, cg_id: str, days: int) -> Chart:
    d = await _cg(http, f"coins/{cg_id}/market_chart", vs_currency="usd", days=days, interval="daily")
    return Chart([p[1] for p in d["prices"]], [p[1] for p in d["market_caps"]])


async def coingecko_global(http) -> dict[str, float]:
    d = await _cg(http, "global")
    return {"btc_dominance": float(d["data"]["market_cap_percentage"]["btc"])}


async def fear_greed(http) -> int:
    return int((await _get(http, FNG, limit=1))["data"][0]["value"])


async def coinalyze_derivs(http, symbols: list[str]) -> dict[str, Derivs]:
    headers = {"api_key": require_secret("coinalyze_key")}
    out: dict[str, Derivs] = {}
    for i in range(0, len(symbols), 20):  # a API aceita até 20 símbolos por chamada
        chunk = symbols[i:i + 20]
        perp = ",".join(f"{s}USDT_PERP.A" for s in chunk)
        now = int(time.time())
        fund = await _get(http, f"{COINALYZE}/funding-rate", headers, symbols=perp)
        await _pause(1.8)  # limite de 35 chamadas por minuto
        oi = await _get(http, f"{COINALYZE}/open-interest", headers, symbols=perp)
        await _pause(1.8)
        liq = await _get(http, f"{COINALYZE}/liquidation-history", headers, symbols=perp,
                         interval="daily", **{"from": now - 2 * 86_400, "to": now})
        await _pause(1.8)
        f = {r["symbol"]: r["value"] for r in fund}
        o = {r["symbol"]: r["value"] for r in oi}
        liqs = {r["symbol"]: (r["history"][-1]["l"] + r["history"][-1]["s"]) if r.get("history") else 0.0 for r in liq}
        for s in chunk:
            k = f"{s}USDT_PERP.A"
            if k in f and k in o:
                out[s] = Derivs(float(f[k]), float(o[k]), float(liqs.get(k, 0.0)))
    return out


async def bgeometrics_btc(http) -> dict[str, float]:
    # o plano grátis devolve o dado com atraso (campo `delayed`) e limita as chamadas: coletar 1 vez por dia
    return {k: float((await _get(http, f"{BGEOMETRICS}/{k}/last"))[k]) for k in ("mvrv", "nupl", "sopr")}


async def fred_latest(http, series_id: str) -> float:
    try:
        d = await _get(http, FRED, series_id=series_id, api_key=require_secret("fred_key"), file_type="json",
                       sort_order="desc", limit=10)
    except httpx.HTTPStatusError as e:  # a FRED só aceita a chave na query: a mensagem original traz a URL
        raise RuntimeError(f"FRED HTTP {e.response.status_code}") from None
    except httpx.HTTPError as e:
        raise RuntimeError(f"FRED {type(e).__name__}") from None
    for o in d["observations"]:  # "." marca dia sem dado
        if o["value"] != ".":
            return float(o["value"])
    raise ValueError(f"FRED {series_id}: sem observação válida")


async def tftc_etf_flows(http) -> list[dict]:
    return [{"day": r["day"], "net_usd": float(r["net_usd"])} for r in await _get(http, TFTC_URL)]


async def defillama_stablecoins(http) -> float:
    d = await _get(http, DEFILLAMA, includePrices="false")
    return float(sum(a["circulating"].get("peggedUSD") or 0 for a in d["peggedAssets"]))


def usdt_bases(markets: dict) -> set[str]:
    """Ativos com par SYMBOL/USDT ativo na corretora."""
    return {k.split("/")[0] for k, m in markets.items() if k.endswith("/USDT") and m.get("active") is not False}


async def delisting_flags(http, clients, symbols: list[str]) -> dict[str, DelistInfo]:
    active: list[set[str]] = []
    for c in clients.values():
        markets = await c.ex.load_markets()
        active.append(usdt_bases(markets))
    try:
        d = await _get(http, BINANCE_PRODUCTS_URL, includeEtf="true")
        tagged = {p["b"] for p in d["data"] if "Monitoring" in (p.get("tags") or [])}
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        tagged = None  # sem fonte: a Monitoring Tag fica desconhecida
    return {s: DelistInfo(None if tagged is None else s in tagged, sum(s in a for a in active)) for s in symbols}
