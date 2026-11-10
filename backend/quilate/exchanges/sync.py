import logging
import sqlite3
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from quilate.exchanges.client import ExchangeClient, Holding, UnsafeKeyError
from quilate.exchanges.cost_basis import Trade
from quilate.exchanges.symbols import normalize_asset

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    ok: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def _normalize(holdings: list[Holding], aliases: dict[str, str]) -> dict[tuple[str, str], float]:
    """Soma por (símbolo canônico, carteira). Ativos LD* da Binance viram carteira earn."""
    syms = {h.symbol.upper() for h in holdings}
    known = {s for s in syms if not (s.startswith("LD") and s[2:] in syms)}
    out: dict[tuple[str, str], float] = defaultdict(float)
    for h in holdings:
        sym = normalize_asset(h.symbol, known, aliases)
        wallet = "earn" if sym != h.symbol.upper() and h.symbol.upper().startswith("LD") and h.wallet == "spot" else h.wallet
        out[(sym, wallet)] += h.qty
    return out


QTY_TOLERANCE = 1e-8
_OTHER_SOURCE = {"api": "csv", "csv": "api"}


def insert_trades(conn: sqlite3.Connection, trades: list[Trade]) -> int:
    """Grava trades e devolve quantos entraram. Não faz commit.

    O mesmo trade vindo da API e do CSV entra uma vez só: a linha é descartada quando a outra fonte já tem
    trade com a mesma corretora, moeda, lado, segundo e quantidade (diferença de até 1e-8). Os ids não
    servem para isso: o CSV da Binance e da MEXC não tem id. Repetido da mesma fonte cai no INSERT OR IGNORE.
    """
    # ponytail: uma consulta por trade, troque por consulta em lote se o CSV passar de dezenas de milhares de linhas
    rows = []
    for t in trades:
        other = _OTHER_SOURCE.get(t.source)
        # o CSV traz o segundo, a API traz milissegundos: compara os 19 primeiros caracteres (até o segundo)
        if other and conn.execute(
                "SELECT 1 FROM trades WHERE exchange=? AND symbol=? AND side=? AND source=?"
                " AND substr(ts_utc, 1, 19)=? AND abs(qty - ?) <= ?",
                (t.exchange, t.symbol, t.side, other, t.ts_utc.isoformat()[:19], t.qty, QTY_TOLERANCE)).fetchone():
            continue
        rows.append((t.exchange, t.trade_id, t.symbol, t.side, t.qty, t.price_usd, t.fee_usd,
                     t.ts_utc.isoformat(), t.source))
    before = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return conn.total_changes - before


async def _sync_one(conn: sqlite3.Connection, name: str, c: ExchangeClient, aliases: dict[str, str], now: datetime) -> None:
    positions = _normalize(await c.fetch_holdings(), aliases)
    row = conn.execute("SELECT max(ts_utc) FROM trades WHERE exchange=? AND source='api'", (name,)).fetchone()
    since = datetime.fromisoformat(row[0]) if row[0] else None
    # também as moedas que sumiram do saldo e as que já têm trade: venda total entre duas sincronizações
    # some do saldo, e sem isso a venda nunca seria buscada
    symbols = {s for s, _ in positions}
    for sql in ("SELECT DISTINCT symbol FROM positions WHERE exchange=?", "SELECT DISTINCT symbol FROM trades WHERE exchange=?"):
        symbols |= {r[0] for r in conn.execute(sql, (name,))}
    trades = [t for sym in sorted(symbols) for t in await c.fetch_trades(sym, since)]
    with conn:  # só grava depois de buscar tudo: falha no meio não apaga as posições antigas
        conn.execute("DELETE FROM positions WHERE exchange=?", (name,))
        conn.executemany("INSERT INTO positions VALUES (?,?,?,?,?,0)",
                         [(name, s, w, q, now.isoformat()) for (s, w), q in positions.items()])
        insert_trades(conn, trades)


async def sync_all(conn: sqlite3.Connection, clients: dict[str, ExchangeClient],
                   notify: Callable[[str], Awaitable[None]], now: datetime,
                   aliases: dict[str, str] | None = None) -> SyncReport:
    """Sincroniza cada corretora de forma isolada. Chave insegura interrompe tudo (UnsafeKeyError)."""
    if aliases is None:
        from quilate.config import load_settings
        aliases = load_settings().symbol_aliases
    report = SyncReport()

    async def fail(name: str, e: Exception) -> None:
        # só o tipo: a mensagem do ccxt pode trazer a URL assinada. O ccxt não expõe o código HTTP na exceção
        report.failed[name] = type(e).__name__
        log.warning("falha ao sincronizar %s (%s)", name, report.failed[name])
        with conn:
            conn.execute("UPDATE positions SET stale=1 WHERE exchange=?", (name,))
        try:
            await notify(f"Falha ao sincronizar {name.capitalize()}: {report.failed[name]}")
        except Exception:
            log.exception("falha ao enviar o alerta de %s", name)

    # Verifica todas as chaves antes de gravar qualquer coisa.
    usable = {}
    for name, c in clients.items():
        try:
            await c.check_read_only()
            usable[name] = c
        except UnsafeKeyError:
            raise
        except Exception as e:
            await fail(name, e)
    for name, c in usable.items():
        try:
            await _sync_one(conn, name, c, aliases, now)
            report.ok.append(name)
        except Exception as e:
            await fail(name, e)
    return report
