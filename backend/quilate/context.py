import asyncio
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from quilate.ai.claude import Claude
from quilate.config import Settings
from quilate.exchanges.live import PriceBook


@dataclass
class AppContext:
    """Tudo que os ciclos, a API e o bot compartilham."""
    settings: Settings
    conn: sqlite3.Connection
    clients: dict  # nome da corretora -> ExchangeClient
    book: PriceBook
    claude: Claude
    embedder: Any
    http: Any  # httpx.AsyncClient
    bot: Any  # quilate.telegram.bot.Bot
    hub: Any  # quilate.api.hub.Hub, ou None fora do servir
    # run_mentions lê mentions_done antes de chamar a IA e grava depois: duas rodadas juntas duplicariam menções.
    # asyncio.Lock do 3.12 só se prende a um loop no primeiro uso, e o ctx vive num loop só
    mentions_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # sync_all zera o estado do cliente da corretora no início: duas rodadas juntas pisariam uma na outra
    sync_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # a página Configuração pede o reinício: o servir encerra o uvicorn e o main troca o processo pelo mesmo comando
    stop_server: Any = None  # callable, preenchido pelo servir
    restart_requested: bool = False
