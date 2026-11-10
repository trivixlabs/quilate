import shutil
from pathlib import Path

import quilate
from quilate.config import DEFAULT_PATH, load_settings
from quilate.secrets import SECRET_NAMES


def test_defaults_match_spec(tmp_path):
    s = load_settings(shutil.copy(DEFAULT_PATH, tmp_path / "config.toml"))
    assert s.tz == "America/Sao_Paulo"
    assert s.budget_usd == 50 and s.budget_alert_ratio == 0.8
    assert s.dust_usd == 10 and s.cutoff_hour == 12 and s.intraday_move == 0.10
    assert s.analyst_username == "" and s.analyst_name == "" and s.trigger_topic == 0 and s.group_topics == {}
    t = s.thresholds
    assert (t.s1_ret_90d, t.s2_drawdown, t.s3_vol_ratio, t.s3_pos_mult, t.s3_spread) == (-0.20, 0.85, 0.5, 20, 0.01)
    assert (t.s4_unlock_90d, t.s4_inflation, t.s6_silence_days, t.s7_low, t.s7_high, t.s7_near_high) == (0.03, 0.10, 90, 0.3, 3.0, 0.9)
    assert s.prices["claude-sonnet-5-5"].input == 2.0 and s.prices["claude-sonnet-5-5"].output == 10.0
    assert s.prices["claude-opus-5-5"].input == 4.0 and s.prices["claude-haiku-5-5"].input == 0.10
    assert s.confirmed_read_only == frozenset()  # MEXC e Gate só entram com confirmação do dono


def test_local_file_overrides_base_and_replaces_whole_table(tmp_path):
    base = Path(shutil.copy(DEFAULT_PATH, tmp_path / "config.toml"))
    (tmp_path / "config.local.toml").write_text(
        'analyst_username = "usuario_do_analista"\ntrigger_topic = 5\nconfirmed_read_only = ["mexc"]\n[group_topics]\n5 = "ANÁLISES"\n', encoding="utf-8")
    s = load_settings(base)
    assert s.analyst_username == "usuario_do_analista" and s.trigger_topic == 5
    assert s.group_topics == {5: "ANÁLISES"}
    assert s.confirmed_read_only == frozenset({"mexc"})
    assert s.budget_usd == 50  # o que o local não cita continua vindo da base


def test_example_local_file_loads(tmp_path):
    example = DEFAULT_PATH.with_name("config.local.example.toml")
    base = Path(shutil.copy(DEFAULT_PATH, tmp_path / "config.toml"))
    shutil.copy(example, tmp_path / "config.local.toml")
    s = load_settings(base)  # nenhuma chave do exemplo é desconhecida
    assert s.analyst_username == "usuario_do_analista" and s.analyst_name == "Ana"
    assert s.trigger_topic == 101 and s.group_topics == {101: "MARKET UPDATES", 102: "GENERAL"}
    assert "confirmed_read_only" in example.read_text(encoding="utf-8")


def test_config_has_no_secret_or_personal_values():
    text = (Path(quilate.__file__).parent / "config.toml").read_text()
    for name in SECRET_NAMES:
        assert f"{name} =" not in text
    assert 'analyst_username = ""' in text


def test_suite_ignores_the_owners_local_file(tmp_path):
    """Dentro dos testes, `load_settings()` sem caminho lê só o config.toml versionado (cópia do conftest)."""
    package = Path(quilate.__file__).parent
    fake_local = 'budget_usd = 20\ncutoff_hour = 9\ndust_usd = 5\nintraday_move = 0.05\n'
    (tmp_path / "config.local.toml").write_text(fake_local, encoding="utf-8")
    base = Path(shutil.copy(package / "config.toml", tmp_path / "config.toml"))
    assert load_settings(base).budget_usd == 20  # com caminho, o local ao lado vale
    import quilate.config as config
    assert config.DEFAULT_PATH.parent != package
    assert not config.DEFAULT_PATH.with_name("config.local.toml").exists()
    s = load_settings()
    assert (s.budget_usd, s.cutoff_hour, s.dust_usd, s.intraday_move) == (50, 12, 10, 0.10)
