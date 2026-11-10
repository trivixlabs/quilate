import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "config.toml"


@dataclass(frozen=True)
class Thresholds:
    s1_ret_90d: float
    s2_drawdown: float
    s3_vol_ratio: float
    s3_pos_mult: float
    s3_spread: float
    s4_unlock_90d: float
    s4_inflation: float
    s6_silence_days: int
    s7_low: float
    s7_high: float
    s7_near_high: float


@dataclass(frozen=True)
class ModelPrice:
    input: float
    output: float
    cache_read: float
    cache_write_1h: float
    long_prompt_tokens: int | None = None  # acima disso o pedido inteiro paga `long_prompt_mult`
    long_prompt_mult: float = 1.0


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    tz: str
    budget_usd: float
    budget_alert_ratio: float
    dust_usd: float
    analyst_username: str
    cutoff_hour: int
    intraday_move: float
    thresholds: Thresholds
    prices: dict[str, ModelPrice]
    symbol_aliases: dict[str, str]
    ambiguous_tickers: frozenset[str]
    confirmed_read_only: frozenset[str]  # MEXC e Gate: o dono confirmou no site que a chave é somente leitura
    owner_name: str = ""  # nome de exibição do dono; só aparece na tela
    sync_minutes: int = 5  # intervalo da sincronização das corretoras e da checagem intradiária
    analyst_name: str = ""  # nome de exibição do analista; vazio, os textos dizem "o analista"
    group_topics: dict[int, str] = field(default_factory=dict)  # só na configuração local
    trigger_topic: int = 0  # 0: sem tópico de gatilho, o ciclo diário roda só pelo horário limite

    @property
    def db_path(self) -> Path:
        return self.data_dir / "quilate.sqlite"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


def load_settings(path: Path | None = None) -> Settings:
    """Lê `config.toml` e, se existir ao lado, `config.local.toml` por cima.

    O arquivo local fica fora do Git e guarda o que identifica o grupo e as pessoas.
    Uma tabela (`[group_topics]`) do arquivo local substitui a tabela inteira.
    """
    base = path or DEFAULT_PATH
    raw = tomllib.loads(base.read_text(encoding="utf-8"))
    local = base.with_name("config.local.toml")
    if local.exists():
        extra = tomllib.loads(local.read_text(encoding="utf-8"))
        unknown = sorted(k for k in extra if k not in raw and k not in LOCAL_KEYS and k != "group_topics")
        if unknown:
            raise ValueError(f"Chave desconhecida em {local.name}: {', '.join(unknown)}")
        raw.update(extra)
    return Settings(
        data_dir=Path(raw["data_dir"]).expanduser(),
        tz=raw["tz"],
        budget_usd=raw["budget_usd"],
        budget_alert_ratio=raw["budget_alert_ratio"],
        dust_usd=raw["dust_usd"],
        analyst_username=raw["analyst_username"],
        analyst_name=raw.get("analyst_name", ""),
        group_topics={int(k): v for k, v in raw.get("group_topics", {}).items()},
        trigger_topic=raw.get("trigger_topic", 0),
        cutoff_hour=raw["cutoff_hour"],
        intraday_move=raw["intraday_move"],
        thresholds=Thresholds(**raw["thresholds"]),
        prices={k: ModelPrice(**v) for k, v in raw["prices"].items()},
        symbol_aliases=dict(raw["symbol_aliases"]),
        ambiguous_tickers=frozenset(raw["ambiguous_tickers"]),
        confirmed_read_only=frozenset(raw["confirmed_read_only"]),
        owner_name=raw.get("owner_name", ""),
        sync_minutes=int(raw.get("sync_minutes", 5)),
    )


# Chaves que a página Configuração pode gravar no config.local.toml. O resto do arquivo é preservado.
LOCAL_KEYS = ("owner_name", "analyst_username", "analyst_name", "confirmed_read_only", "budget_usd", "budget_alert_ratio",
              "dust_usd", "cutoff_hour", "intraday_move", "sync_minutes")
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)  # os escapes do JSON valem numa string básica do TOML
    if isinstance(v, list | tuple | set | frozenset):
        return "[" + ", ".join(_toml_value(x) for x in sorted(v, key=str)) + "]"
    raise TypeError(f"valor sem forma TOML: {type(v).__name__}")


def _toml_key(k) -> str:
    return k if _BARE_KEY.match(str(k)) else json.dumps(str(k), ensure_ascii=False)


def save_local(updates: dict, path: Path | None = None) -> Path:
    """Grava `updates` em `config.local.toml` por cima do que já existe. Tabelas (`[group_topics]`) são mantidas.

    Comentários do arquivo são perdidos: o modelo com as explicações fica em `config.local.example.toml`.
    """
    local = (path or DEFAULT_PATH).with_name("config.local.toml")
    raw = tomllib.loads(local.read_text(encoding="utf-8")) if local.exists() else {}
    raw.update(updates)
    lines = ["# Fora do Git. Sobrepõe config.toml. A página Configuração reescreve este arquivo."]
    lines += [f"{_toml_key(k)} = {_toml_value(v)}" for k, v in raw.items() if not isinstance(v, dict)]
    for name, table in raw.items():
        if isinstance(table, dict):
            lines += ["", f"[{_toml_key(name)}]"] + [f"{_toml_key(k)} = {_toml_value(v)}" for k, v in table.items()]
    local.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return local
