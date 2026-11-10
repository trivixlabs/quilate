from quilate.exchanges.symbols import normalize_asset

KNOWN = {"BTC", "ETH", "LDO", "POL", "ARB"}


def test_binance_earn_prefix():
    assert normalize_asset("LDBTC", KNOWN, {}) == "BTC"


def test_lido_is_not_earn():
    assert normalize_asset("LDO", KNOWN, {}) == "LDO"


def test_aliases():
    assert normalize_asset("MATIC", KNOWN, {"MATIC": "POL"}) == "POL"
    assert normalize_asset("xbt", KNOWN, {"XBT": "BTC"}) == "BTC"


def test_ld_prefix_kept_when_rest_unknown():
    assert normalize_asset("LDXYZ", KNOWN, {}) == "LDXYZ"
