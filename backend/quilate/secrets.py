import keyring
import keyring.errors

SERVICE = "quilate"

SECRET_NAMES: tuple[str, ...] = (
    "binance_key", "binance_secret", "mexc_key", "mexc_secret",
    "bybit_key", "bybit_secret", "gate_key", "gate_secret",
    "anthropic_api_key", "telegram_api_id", "telegram_api_hash", "telegram_session",
    "telegram_group_id", "telegram_bot_token", "telegram_chat_id",
    "coingecko_key", "coinalyze_key", "fred_key", "coinglass_key",
    "hf_token",  # Hugging Face: download do EmbeddingGemma, no lugar do huggingface-cli login
)


class MissingSecret(RuntimeError):
    pass


def get_secret(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def set_secret(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def delete_secret(name: str) -> None:
    try:
        keyring.delete_password(SERVICE, name)
    except keyring.errors.PasswordDeleteError:
        pass


def require_secret(name: str) -> str:
    value = get_secret(name)
    if not value:
        raise MissingSecret(f"Falta o segredo {name}. Rode: quilate segredo {name}")
    return value
