"""Importa o histórico de trades exportado pelas corretoras (CSV).

Os cabeçalhos seguem o formato documentado de cada corretora e precisam ser
confirmados contra a exportação real (ver README).
"""
import csv
import hashlib
import logging
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from quilate.exchanges.client import STABLES
from quilate.exchanges.cost_basis import Trade
from quilate.exchanges.symbols import normalize_asset

log = logging.getLogger(__name__)


def _split_pair(pair: str) -> tuple[str, str]:
    p = pair.upper().replace("/", "_")
    if "_" in p:
        base, quote = p.split("_", 1)
        return base, quote
    for q in STABLES + ("BTC", "ETH", "BRL", "EUR"):
        if p.endswith(q) and len(p) > len(q):
            return p[: -len(q)], q
    raise ValueError(f"par desconhecido: {pair}")


def _num_ccy(text: str) -> tuple[float, str]:
    m = re.fullmatch(r"\s*([\d.]+)\s*([A-Za-z]*)\s*", text)
    if not m:
        raise ValueError(f"valor inválido: {text}")
    return float(m.group(1)), m.group(2).upper()


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.strip()).replace(tzinfo=UTC)


def _trade(exchange, trade_id, pair, side, qty, price, fee, fee_ccy, ts, aliases, salt=""):
    """None quando a cotação não é USDT/USDC (sem preço em USD no CSV)."""
    base, quote = _split_pair(pair)
    if quote not in STABLES:
        log.warning("%s: par %s ignorado, cotação %s sem preço em USD", exchange, pair, quote)
        return None
    if fee_ccy in ("", quote):
        fee_usd = fee
    elif fee_ccy == base:
        fee_usd = fee * price
    else:
        fee_usd = 0.0  # taxa em BNB ou outra moeda: o CSV não traz a cotação dela
        if fee:
            log.warning("%s: taxa de %s %s no trade de %s ignorada; o preço médio fica um pouco abaixo do real",
                        exchange, fee, fee_ccy, pair)
    tid = trade_id or hashlib.sha1(f"{exchange}|{salt}".encode()).hexdigest()[:16]
    return Trade(exchange, tid, normalize_asset(base, set(), aliases), side.lower(), qty, price, fee_usd, ts, "csv")


def _binance(r, aliases, salt):
    qty, _ = _num_ccy(r["Executed"])
    fee, fee_ccy = _num_ccy(r["Fee"])
    return _trade("binance", None, r["Pair"], r["Side"], qty, float(r["Price"]), fee, fee_ccy, _ts(r["Date(UTC)"]), aliases, salt)


def _mexc(r, aliases, salt):  # taxa na moeda de cotação
    return _trade("mexc", None, r["Pairs"], r["Side"], float(r["Executed Amount"]), float(r["Filled Price"]),
                  float(r["Fee"]), "", _ts(r["Time"]), aliases, salt)


def _bybit(r, aliases, salt):  # taxa na moeda de cotação
    return _trade("bybit", r["Transaction ID"], r["Spot Pairs"], r["Direction"], float(r["Filled Quantity"]),
                  float(r["Filled Price"]), float(r["Fees"]), "", _ts(r["Filled Time(UTC)"]), aliases, salt)


def _gate(r, aliases, salt):
    return _trade("gate", r["No"], r["Currency_Pair"], r["Action"], float(r["Amount"]), float(r["Price"]),
                  float(r["Fee"]), r["Fee Currency"].upper(), _ts(r["Time"]), aliases, salt)


_PARSERS = {"binance": _binance, "mexc": _mexc, "bybit": _bybit, "gate": _gate}


def parse_csv(exchange: str, path: Path, aliases: dict[str, str] | None = None) -> list[Trade]:
    parse = _PARSERS[exchange]
    with open(path, newline="", encoding="utf-8-sig") as f:
        seen: Counter = Counter()
        trades = []
        reader = csv.DictReader(f)
        for row in reader:
            # id estável entre exportações: conteúdo da linha + k-ésima ocorrência dela no arquivo
            content = "|".join(row.get(k) or "" for k in reader.fieldnames)  # ignora colunas extras
            salt = f"{content}#{seen[content]}"
            seen[content] += 1
            trades.append(parse(row, aliases or {}, salt))
        return [t for t in trades if t]
