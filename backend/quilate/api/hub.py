"""Difusão de eventos para os WebSockets abertos."""
import asyncio
import time
from collections.abc import Awaitable, Callable

from starlette.websockets import WebSocketState

TICK_GAP = 0.5  # no máximo 2 ticks por segundo por moeda


class Hub:
    def __init__(self, now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.sockets: set = set()
        self._last: dict[str, float] = {}
        self._pending: dict[str, dict] = {}  # último tick segurado pelo limite, por moeda
        self._timers: dict[str, asyncio.Task] = {}
        self._now, self._sleep = now, sleep

    def add(self, ws) -> None:
        self.sockets.add(ws)

    def discard(self, ws) -> None:
        self.sockets.discard(ws)

    async def broadcast(self, event: dict) -> None:
        if event.get("type") == "tick":  # só tick tem limite; veredito e ciclo passam sempre
            sym, t = event["symbol"], self._now()
            wait = self._last.get(sym, -TICK_GAP) + TICK_GAP - t
            if wait > 0:  # dentro da janela: guarda o mais novo e envia quando ela fechar
                self._pending[sym] = event
                if sym not in self._timers:
                    self._timers[sym] = asyncio.create_task(self._flush(sym, wait))
                return
            self._pending.pop(sym, None)  # este é mais novo que o guardado
            if timer := self._timers.pop(sym, None):  # o timer velho dispararia cedo na janela nova
                timer.cancel()
            self._last[sym] = t
        await self._send(event)

    async def _flush(self, sym: str, wait: float) -> None:
        await self._sleep(wait)
        self._timers.pop(sym, None)
        event = self._pending.pop(sym, None)
        if event is not None:
            self._last[sym] = self._now()
            await self._send(event)

    async def _send(self, event: dict) -> None:
        for ws in list(self.sockets):
            if getattr(ws, "application_state", WebSocketState.CONNECTED) != WebSocketState.CONNECTED:
                continue  # ainda no aperto de mão: não é erro
            try:
                await ws.send_json(event)
            except Exception:  # socket morto sai da lista
                self.sockets.discard(ws)
