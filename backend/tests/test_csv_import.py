from datetime import datetime
from pathlib import Path

import pytest

from quilate.exchanges.csv_import import parse_csv

FIXT = Path(__file__).parent / "fixtures" / "csv"


@pytest.mark.parametrize("ex", ["binance", "mexc", "bybit", "gate"])
def test_csv_fixture(ex):
    trades = parse_csv(ex, FIXT / f"{ex}.csv")
    assert len(trades) == 2
    t = trades[0]
    assert (t.side, t.source, t.exchange, t.symbol) == ("buy", "csv", ex, t.symbol)
    assert t.symbol in ("BTC", "SOL")
    assert t.qty > 0 and t.price_usd > 0 and t.ts_utc == datetime.fromisoformat("2025-01-10T12:00:00+00:00")
    assert trades[1].side == "sell"


def test_binance_fee_in_base_converted():
    t = parse_csv("binance", FIXT / "binance.csv")[0]
    assert t.qty == 0.01 and t.fee_usd == pytest.approx(0.5)


def test_fee_in_another_currency_is_zero_with_a_warning(tmp_path, caplog):
    p = tmp_path / "b.csv"
    p.write_text("Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n2025-01-10 12:00:00,BTCUSDT,BUY,50000,0.01BTC,500USDT,0.001BNB\n")
    with caplog.at_level("WARNING"):
        [t] = parse_csv("binance", p)
    assert t.fee_usd == 0.0 and "BNB" in caplog.text and "ignorada" in caplog.text


def test_identical_rows_without_id_are_kept(tmp_path):
    row = "2025-01-10 12:00:00,BTCUSDT,BUY,50000,0.01BTC,500USDT,0.5USDT\n"
    f = tmp_path / "b.csv"
    f.write_text("Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n" + row * 2)
    ids = {t.trade_id for t in parse_csv("binance", f)}
    assert len(ids) == 2


def test_ids_stable_across_overlapping_exports(tmp_path):
    head = "Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n"
    a = "2025-01-10 12:00:00,BTCUSDT,BUY,50000,0.01BTC,500USDT,0.5USDT\n"
    b = "2025-02-11 13:30:00,ETHUSDT,SELL,3000,0.5ETH,1500USDT,1.5USDT\n"
    new = "2025-03-01 09:00:00,SOLUSDT,BUY,100,1SOL,100USDT,0.1USDT\n"
    f1, f2 = tmp_path / "1.csv", tmp_path / "2.csv"
    f1.write_text(head + a + a + b)
    f2.write_text(head + new + b + a + a)
    ids1 = [t.trade_id for t in parse_csv("binance", f1)]
    ids2 = {t.symbol + t.side: t.trade_id for t in parse_csv("binance", f2)}
    assert len(set(ids1)) == 3
    assert ids1[2] in ids2.values() and set(ids1[:2]) <= {t.trade_id for t in parse_csv("binance", f2)}


def test_extra_trailing_column_imports_with_same_id(tmp_path):
    head = "Date(UTC),Pair,Side,Price,Executed,Amount,Fee\n"
    row = "2025-01-10 12:00:00,BTCUSDT,BUY,50000,0.01BTC,500USDT,0.5USDT"
    f1, f2 = tmp_path / "1.csv", tmp_path / "2.csv"
    f1.write_text(head + row + "\n")
    f2.write_text(head + row + ",extra\n")
    assert parse_csv("binance", f1)[0].trade_id == parse_csv("binance", f2)[0].trade_id
