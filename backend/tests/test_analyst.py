from dataclasses import replace

import pytest

from quilate import analyst
from quilate.config import DEFAULT_PATH, load_settings

BASE = replace(load_settings(), analyst_name="", analyst_username="usuario_do_analista")


def test_generic_reference_without_name():
    s = replace(BASE, analyst_name="")
    assert analyst.subject(s) == "O analista" and analyst.of(s) == "do analista"


def test_named_reference_is_raw_text():
    # o escape é feito uma vez só, no ponto de saída (bot e prompts)
    s = replace(BASE, analyst_name=' Ana <b>&"x" ')
    assert analyst.subject(s) == 'Ana <b>&"x"'
    assert analyst.of(s) == 'de Ana <b>&"x"'
    assert analyst.subject(replace(BASE, analyst_name="  ")) == "O analista"


def test_versioned_config_names_no_group():
    raw = DEFAULT_PATH.read_text()
    assert "trigger_topic = 0" in raw and "[group_topics]" not in raw


def test_unknown_key_in_local_file_is_reported(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text(DEFAULT_PATH.read_text())
    base.with_name("config.local.toml").write_text('analist_username = "x"\n')
    with pytest.raises(ValueError, match=r"config\.local\.toml.*analist_username"):
        load_settings(base)
