import atexit
import shutil
import tempfile
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

import quilate.config as config

# Antes da coleta, e também no subprocesso que importa este arquivo: `load_settings()` sem caminho lê só o
# config.toml versionado, de uma cópia sem config.local.toml ao lado. Os valores do dono não mudam o teste.
PACKAGE_LOCAL = config.DEFAULT_PATH.with_name("config.local.toml")
_isolated_dir = Path(tempfile.mkdtemp(prefix="quilate-config-"))
atexit.register(shutil.rmtree, _isolated_dir, True)
for _name in ("config.toml", "config.local.example.toml"):
    shutil.copy(config.DEFAULT_PATH.with_name(_name), _isolated_dir / _name)
config.DEFAULT_PATH = _isolated_dir / "config.toml"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        try:
            del self.store[(service, username)]
        except KeyError:
            raise PasswordDeleteError(username) from None


@pytest.fixture
def memory_keyring():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def db(tmp_path):
    from quilate.db import connect, migrate

    conn = connect(tmp_path / "t.db")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def package_local_config_untouched():
    """Nenhum teste pode gravar o config.local.toml real do pacote: ele guarda o que identifica o grupo."""
    before = PACKAGE_LOCAL.read_bytes() if PACKAGE_LOCAL.exists() else None
    yield
    after = PACKAGE_LOCAL.read_bytes() if PACKAGE_LOCAL.exists() else None
    assert before == after, "o teste gravou em quilate/config.local.toml; use local_config=tmp_path no create_app"
    stray = config.DEFAULT_PATH.with_name("config.local.toml")
    wrote = stray.exists()
    stray.unlink(missing_ok=True)  # sem isso, uma sobra derruba todos os testes seguintes
    assert not wrote, "o teste gravou um config.local.toml ao lado do config.toml isolado; passe um caminho"
