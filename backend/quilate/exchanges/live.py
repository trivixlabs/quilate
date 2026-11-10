import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class Tick:
    exchange: str
    symbol: str
    last: float
    ts_ms: int


class PriceBook:
    """Último preço por símbolo: vale o tick mais recente entre as corretoras."""

    def __init__(self):
        self._t: dict[str, Tick] = {}

    def update(self, t: Tick) -> None:
        cur = self._t.get(t.symbol)
        if cur is None or t.ts_ms >= cur.ts_ms:
            self._t[t.symbol] = t

    def last(self, symbol: str) -> float | None:
        t = self._t.get(symbol)
        return t.last if t else None


async def _watch(client, symbols, book, on_tick, stop):
    wait = 1
    while not stop.is_set():
        try:
            ticks = await client.watch_tickers(symbols)
            wait = 1
        except Exception as e:  # reconecta com espera exponencial, de 1 s a 60 s
            log.warning("%s: %s, nova tentativa em %s s", client.name, e, wait)
            await asyncio.sleep(wait)
            wait = min(wait * 2, 60)
            continue
        for t in ticks:
            try:
                book.update(t)
                await on_tick(t)
            except Exception:
                log.exception("%s: on_tick falhou, o feed continua", client.name)


async def run_live(clients, symbols_by_exchange: dict[str, list[str]], book: PriceBook,
                   on_tick: Callable[[Tick], Awaitable[None]], stop: asyncio.Event) -> None:
    """Uma tarefa por corretora; termina quando `stop` é acionado."""
    tasks = [asyncio.create_task(_watch(clients[n], s, book, on_tick, stop))
             for n, s in symbols_by_exchange.items() if n in clients and s]
    def morreu(t: asyncio.Task) -> None:
        # run_live só cancela depois de `stop`; antes disso, cancelamento ou erro é morte real
        if t.cancelled():
            if not stop.is_set():
                log.error("tarefa do feed cancelada antes do stop")
        elif t.exception():
            log.error("tarefa do feed morreu", exc_info=t.exception())
    for t in tasks:
        t.add_done_callback(morreu)
    stopper = asyncio.create_task(stop.wait())
    try:
        await stopper  # a única saída é `stop`: uma tarefa que morre não derruba as outras
    finally:
        for t in (stopper, *tasks):
            t.cancel()
        await asyncio.gather(stopper, *tasks, return_exceptions=True)


async def _smoke(name: str, market: str) -> None:
    import ccxt.async_support as ccxt

    from quilate.exchanges.client import ExchangeClient
    client = ExchangeClient(name, getattr(ccxt, name)({"enableRateLimit": True}))
    base = market.split("/")[0]
    book, stop, n = PriceBook(), asyncio.Event(), 0

    async def show(t: Tick):
        nonlocal n
        n += 1
        print(f"{t.exchange} {t.symbol} {t.last} {t.ts_ms}", flush=True)
        if n >= 5:
            stop.set()
    try:
        await asyncio.wait_for(run_live({name: client}, {name: [base]}, book, show, stop), 60)
    finally:
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--smoke":
        sys.exit("uso: python -m quilate.exchanges.live --smoke <corretora> <BASE/QUOTE>")
    asyncio.run(_smoke(sys.argv[2], sys.argv[3]))
