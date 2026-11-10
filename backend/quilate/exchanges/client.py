import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

import ccxt.async_support as ccxt
import ccxt.pro as ccxtpro

from quilate.config import Settings
from quilate.exchanges.cost_basis import Trade
from quilate.exchanges.live import Tick
from quilate.market.sources import usdt_bases
from quilate.secrets import get_secret

log = logging.getLogger(__name__)
STABLES = ("USDT", "USDC")
QUOTES = ("USDT", "USDC", "BTC", "ETH")
NAMES = ("binance", "mexc", "bybit", "gate")
UNVERIFIED = frozenset({"mexc", "gate"})  # a API não expõe as permissões da chave
MEXC_DAYS = 30  # a API da MEXC só devolve o último mês de trades; o mais antigo entra pelo CSV
MEXC_PAGE = 100  # máximo por página na MEXC
# campos de apiRestrictions da Binance que precisam vir False. Ausente ou outro valor: chave insegura
BINANCE_REQUIRED = ("enableWithdrawals", "enableSpotAndMarginTrading", "enableFutures", "enableMargin",
                    "enableVanillaOptions", "enablePortfolioMarginTrading", "enableInternalTransfer",
                    "permitsUniversalTransfer", "enableFixApiTrade")
BINANCE_ALLOWED = ("enableReading", "enableFixReadOnly")  # só leitura: podem ser True


class UnsafeKeyError(Exception):
    """A chave da corretora permite trade ou saque."""


class UnconfirmedKeyError(UnsafeKeyError):
    """MEXC ou Gate: a API não informa as permissões e o dono ainda não confirmou que a chave é somente leitura."""


@dataclass
class Holding:
    exchange: str
    symbol: str
    wallet: Literal["spot", "earn", "funding"]
    qty: float


@dataclass
class Candle:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume_quote: float


def _ms(dt: datetime | None) -> int | None:
    return int(dt.timestamp() * 1000) if dt else None


class ExchangeClient:
    def __init__(self, name: str, ex: ccxt.Exchange, confirmed: bool = False):
        self.name, self.ex = name, ex
        self.confirmed = confirmed  # o dono confirmou no site que a chave é somente leitura (MEXC e Gate)
        self._usd: dict[str, dict[date, float]] = {}
        self._converts: list[dict] | None = None
        self._polled = False
        self._pro = None  # instância ccxt.pro, criada na primeira chamada de watch_tickers
        self._no_market: set[str] = set()  # moedas sem par USDT ativo já avisadas no log

    async def close(self) -> None:
        try:
            if self._pro:
                await self._pro.close()
        finally:
            await self.ex.close()

    async def watch_tickers(self, symbols: list[str]) -> list[Tick]:
        """Espera o próximo lote de preços (dados públicos, sem chave) de `BASE` em USDT."""
        if self.name == "mexc":
            return await self._poll_tickers(symbols)
        if self._pro is None:
            self._pro = getattr(ccxtpro, self.name)({"enableRateLimit": True})
        # moeda sem par USDT ativo derruba o lote inteiro (BadSymbol): fica de fora. load_markets usa o cache do ccxt
        bases = usdt_bases(await self._pro.load_markets())
        if missing := sorted(set(symbols) - bases - self._no_market):
            log.warning("%s: sem par USDT ativo, fora do preço ao vivo: %s", self.name, ", ".join(missing))
            self._no_market.update(missing)
        pairs = [f"{s}/USDT" for s in symbols if s in bases]
        if not pairs:
            await asyncio.sleep(60)  # nada para assinar: sem isso, o laço do feed gira sem parar
            return []
        data = await self._pro.watch_tickers(pairs)
        now = _ms(datetime.now(UTC))
        return [Tick(self.name, m.split("/")[0], float(t["last"]), int(t.get("timestamp") or now))
                for m, t in data.items() if t.get("last")]

    async def _poll_tickers(self, symbols: list[str]) -> list[Tick]:
        # a MEXC não tem watchTickers para spot no ccxt.pro: consulta a cada 5 s
        if self._polled:
            await asyncio.sleep(5)
        self._polled = True
        out = []
        for s in symbols:
            try:
                t = await self.ex.fetch_ticker(f"{s}/USDT")
                out.append(Tick(self.name, s, float(t["last"]), int(t.get("timestamp") or _ms(datetime.now(UTC)))))
            except Exception as e:  # um símbolo ruim não derruba o lote
                log.warning("mexc: %s sem preço (%s)", s, e)
        return out

    async def fetch_holdings(self) -> list[Holding]:
        self._converts = None  # novo ciclo de sync: refaz o histórico de Convert
        wallets = ["spot", "funding"] if self.name == "binance" else ["spot"]
        out = []
        for wallet in wallets:
            bal = await self.ex.fetch_balance({"type": wallet} if self.name == "binance" else {})
            out += [Holding(self.name, c, wallet, float(q)) for c, q in bal["total"].items() if q and float(q) > 0]
        return out

    async def fetch_daily_candles(self, symbol: str, quote: str, days: int) -> list[Candle]:
        since = _ms(datetime.now(UTC)) - days * 86_400_000
        rows = await self.ex.fetch_ohlcv(f"{symbol}/{quote}", "1d", since, days)
        return [Candle(datetime.fromtimestamp(r[0] / 1000, UTC).date(), *map(float, r[1:5]), float(r[5]) * float(r[4])) for r in rows]

    async def fetch_spread(self, symbol: str) -> float | None:
        t = await self.ex.fetch_ticker(f"{symbol}/USDT")
        if not t.get("bid") or not t.get("ask"):
            return None
        return (t["ask"] - t["bid"]) / ((t["ask"] + t["bid"]) / 2)

    async def check_read_only(self) -> None:
        """Falha fechada: campo ausente também é chave insegura."""
        if self.name == "binance":
            r = await self.ex.sapi_get_account_apirestrictions()
            fields = set(BINANCE_REQUIRED) | {k for k in r if k.startswith(("enable", "permits"))}
            if bad := sorted(k for k in fields - set(BINANCE_ALLOWED) if r.get(k) is not False):
                raise UnsafeKeyError(f"binance: a chave permite trade, saque ou transferência ({', '.join(bad)})")
        elif self.name == "bybit":
            r = await self.ex.private_get_v5_user_query_api()
            if str((r.get("result") or {}).get("readOnly")) != "1":  # 1 = somente leitura, 0 = leitura e escrita
                raise UnsafeKeyError("bybit: a chave permite trade ou saque")
        elif not self.confirmed:
            raise UnconfirmedKeyError(
                f"{self.name}: a API não informa as permissões da chave. Confirme no site da corretora que a chave "
                f"é somente leitura e acrescente \"{self.name}\" a confirmed_read_only em quilate/config.local.toml")

    async def _usd_close(self, asset: str, day: date) -> float | None:
        """Cotação diária do ativo em USDT (1 para stablecoin)."""
        if asset in STABLES:
            return 1.0
        if asset not in self._usd:
            try:
                candles = await self.fetch_daily_candles(asset, "USDT", 1000)
            except ccxt.BaseError:
                candles = []
            self._usd[asset] = {c.day: c.close for c in candles}
        return self._usd[asset].get(day)

    async def fetch_trades(self, symbol: str, since_utc: datetime | None) -> list[Trade]:
        out = []
        await self.ex.load_markets()
        for quote in QUOTES:
            if quote == symbol or f"{symbol}/{quote}" not in self.ex.markets:
                continue
            for r in await self._my_trades(f"{symbol}/{quote}", _ms(since_utc)):
                ts = datetime.fromtimestamp(r["timestamp"] / 1000, UTC)
                q_usd = await self._usd_close(quote, ts.date())
                if q_usd is None:
                    log.warning("%s: sem cotação de %s em %s, trade ignorado", self.name, quote, ts.date())
                    continue
                fee = r.get("fee") or {}
                fee_cost, fee_ccy = float(fee.get("cost") or 0), fee.get("currency")
                if fee_ccy == symbol:
                    fee_usd = fee_cost * r["price"] * q_usd
                elif fee_ccy == quote:
                    fee_usd = fee_cost * q_usd
                elif not (fee_cost and fee_ccy):
                    fee_usd = 0.0
                else:  # terceira moeda (BNB na Binance): fechamento do dia
                    fee_px = await self._usd_close(fee_ccy, ts.date())
                    if fee_px is None:
                        log.warning("%s: sem cotação de %s em %s, taxa do trade %s ficou 0", self.name, fee_ccy, ts.date(), r["id"])
                    fee_usd = fee_cost * (fee_px or 0.0)
                out.append(Trade(self.name, str(r["id"]), symbol, r["side"], float(r["amount"]),
                                 float(r["price"]) * q_usd, fee_usd, ts, "api"))
        if self.name == "binance":
            out += await self._convert_trades(symbol, since_utc)
        return out

    async def _my_trades(self, pair: str, since: int | None) -> list[dict]:
        """Todas as páginas de trades do par. Sem isso, a 1ª sincronização perde as vendas antigas e o custo médio erra."""
        if self.name != "mexc":
            # o ccxt pagina Binance, Bybit e Gate; paginationCalls alto para não cortar histórico longo em silêncio
            return await self.ex.fetch_my_trades(pair, since, None, {"paginate": True, "paginationCalls": 1000})
        # o ccxt não pagina a MEXC: avança `since` até vir uma página incompleta
        since = since or _ms(datetime.now(UTC)) - MEXC_DAYS * 86_400_000
        out, seen = [], set()
        while True:
            page = await self.ex.fetch_my_trades(pair, since, MEXC_PAGE)
            new = [r for r in page if r["id"] not in seen]  # o mesmo milissegundo volta na página seguinte
            seen.update(r["id"] for r in new)
            out += new
            if len(page) < MEXC_PAGE or not new:
                return out
            since = max(r["timestamp"] for r in page)

    async def _all_converts(self, since_utc: datetime | None) -> list[dict]:
        """Histórico de Convert, buscado uma vez por sync."""
        if self._converts is None:
            found: list[dict] = []
            end = _ms(datetime.now(UTC))
            t0 = _ms(since_utc) or end - 365 * 86_400_000
            step = 30 * 86_400_000  # a API aceita no máximo 30 dias por consulta
            while t0 < end:
                t1 = min(t0 + step, end)
                r = await self.ex.sapi_get_convert_tradeflow({"startTime": t0, "endTime": t1})
                found += r.get("list", [])
                t0 = t1
            self._converts = found
        return self._converts

    async def _convert_trades(self, symbol: str, since_utc: datetime | None) -> list[Trade]:
        """Cada Convert vira uma venda do ativo de origem e uma compra do de destino, com o mesmo valor em USD."""
        out = []
        for c in await self._all_converts(since_utc):
            if c.get("orderStatus") not in (None, "SUCCESS") or symbol not in (c["fromAsset"], c["toAsset"]):
                continue
            ts = datetime.fromtimestamp(int(c["createTime"]) / 1000, UTC)
            f_amt, t_amt = float(c["fromAmount"]), float(c["toAmount"])
            f_px = await self._usd_close(c["fromAsset"], ts.date())
            t_px = await self._usd_close(c["toAsset"], ts.date())
            usd = f_amt * f_px if f_px is not None else t_amt * t_px if t_px is not None else None
            if usd is None:
                log.warning("binance: Convert %s sem cotação, ignorado", c["orderId"])
                continue
            if c["fromAsset"] == symbol:
                out.append(Trade("binance", f"convert-{c['orderId']}-sell", symbol, "sell", f_amt, usd / f_amt, 0.0, ts, "api"))
            else:
                out.append(Trade("binance", f"convert-{c['orderId']}-buy", symbol, "buy", t_amt, usd / t_amt, 0.0, ts, "api"))
        return out


def make_clients(settings: Settings) -> dict[str, ExchangeClient]:
    """Só cria cliente para a corretora que tem chave no Keychain."""
    clients = {}
    for name in NAMES:
        key, secret = get_secret(f"{name}_key"), get_secret(f"{name}_secret")
        if key and secret:
            ex = getattr(ccxt, name)({"apiKey": key, "secret": secret, "enableRateLimit": True})
            clients[name] = ExchangeClient(name, ex, confirmed=name in settings.confirmed_read_only)
    return clients
