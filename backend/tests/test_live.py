import asyncio

from quilate.exchanges.client import ExchangeClient
from quilate.exchanges.live import PriceBook, Tick, run_live


def tick(sym, last, ex="binance"):
    return Tick(ex, sym, last, 1)


class FakeLiveClient:
    def __init__(self, name, batches):
        self.name, self.batches = name, list(batches)

    async def watch_tickers(self, symbols):
        b = self.batches.pop(0)
        if isinstance(b, Exception):
            raise b
        return b


async def test_ticks_flow_and_reconnect(monkeypatch):
    async def no_wait(_):
        pass
    monkeypatch.setattr("quilate.exchanges.live.asyncio.sleep", no_wait)
    c = FakeLiveClient("binance", batches=[[tick("BTC", 100)], ConnectionError(), [tick("BTC", 101)]])
    book, got, stop = PriceBook(), [], asyncio.Event()

    async def on_tick(t):
        got.append(t.last)
        if len(got) == 2:
            stop.set()
    await asyncio.wait_for(run_live({"binance": c}, {"binance": ["BTC"]}, book, on_tick, stop), 2)
    assert got == [100, 101] and book.last("BTC") == 101


def test_book_keeps_most_recent_across_exchanges():
    b = PriceBook()
    b.update(Tick("binance", "BTC", 100, 10))
    b.update(Tick("mexc", "BTC", 99, 5))  # mais antigo, ignorado
    assert b.last("BTC") == 100 and b.last("ETH") is None


async def test_client_maps_market_symbols():
    class ProEx:
        async def load_markets(self):
            return {"BTC/USDT": {"active": True}}

        async def watch_tickers(self, syms):
            assert syms == ["BTC/USDT"]
            return {"BTC/USDT": {"last": 5.0, "timestamp": 7}}
    c = ExchangeClient("binance", object())
    c._pro = ProEx()
    assert await c.watch_tickers(["BTC"]) == [Tick("binance", "BTC", 5.0, 7)]


async def test_mexc_polls_ticker(monkeypatch):
    async def no_wait(_):
        pass
    monkeypatch.setattr("quilate.exchanges.client.asyncio.sleep", no_wait)

    class Ex:
        async def fetch_ticker(self, m):
            assert m == "BTC/USDT"
            return {"last": 9, "timestamp": 3}
    c = ExchangeClient("mexc", Ex())
    assert await c.watch_tickers(["BTC"]) == [Tick("mexc", "BTC", 9.0, 3)]
    assert await c.watch_tickers(["BTC"]) == [Tick("mexc", "BTC", 9.0, 3)]


async def test_on_tick_error_does_not_stop_feed(monkeypatch):
    c = FakeLiveClient("binance", batches=[[tick("BTC", 1)], [tick("BTC", 2)]])
    book, got, stop = PriceBook(), [], asyncio.Event()

    async def on_tick(t):
        got.append(t.last)
        if t.last == 1:
            raise RuntimeError("socket fechado")
        stop.set()
    await asyncio.wait_for(run_live({"binance": c}, {"binance": ["BTC"]}, book, on_tick, stop), 2)
    assert got == [1, 2]


async def test_stop_during_backoff_returns_promptly():
    c = FakeLiveClient("binance", batches=[ConnectionError()])
    stop = asyncio.Event()

    async def on_tick(t):
        pass
    asyncio.get_running_loop().call_later(0.1, stop.set)
    await asyncio.wait_for(run_live({"binance": c}, {"binance": ["BTC"]}, PriceBook(), on_tick, stop), 0.5)


async def test_dead_task_does_not_end_other_exchanges(caplog):
    class Dead:
        @property
        def name(self):  # lançar dentro do except de _watch faz a exceção escapar da tarefa
            raise ValueError("morreu")

        async def watch_tickers(self, s):
            raise ConnectionError()

    class Slow:
        name = "binance"
        n = 0

        async def watch_tickers(self, s):
            self.n += 1
            await asyncio.sleep(0.05)
            return [tick("BTC", self.n)]
    got, stop = [], asyncio.Event()

    async def on_tick(t):
        got.append(t.last)
    run = asyncio.create_task(run_live({"binance": Slow(), "bybit": Dead()},
                                       {"binance": ["BTC"], "bybit": ["BTC"]}, PriceBook(), on_tick, stop))
    await asyncio.sleep(0.2)  # bybit já morreu; binance segue entregando
    n = len(got)
    await asyncio.sleep(0.2)
    assert not run.done() and len(got) > n >= 1
    assert "tarefa do feed morreu" in caplog.text
    stop.set()
    await asyncio.wait_for(run, 1)


async def test_pro_path_falls_back_to_now_without_timestamp():
    class ProEx:
        async def load_markets(self):
            return {"BTC/USDT": {"active": True}}

        async def watch_tickers(self, syms):
            return {"BTC/USDT": {"last": 5.0, "timestamp": None}}
    c = ExchangeClient("binance", object())
    c._pro = ProEx()
    [t] = await c.watch_tickers(["BTC"])
    assert t.last == 5.0 and t.ts_ms > 1_700_000_000_000
