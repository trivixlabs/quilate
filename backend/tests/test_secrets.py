import sys
import types

import pytest

from quilate.secrets import SECRET_NAMES, MissingSecret, get_secret, require_secret, set_secret


def test_secret_roundtrip(memory_keyring):
    set_secret("anthropic_api_key", "x")
    assert get_secret("anthropic_api_key") == "x"
    assert get_secret("nao_existe") is None


def test_require_secret_names_the_command(memory_keyring):
    with pytest.raises(MissingSecret, match="quilate segredo fred_key"):
        require_secret("fred_key")
    set_secret("fred_key", "k")
    assert require_secret("fred_key") == "k"


def test_hf_token_goes_to_the_model_loader(memory_keyring, monkeypatch):
    """R40: o token do Hugging Face sai do Keychain, nunca de ~/.cache/huggingface/token."""
    assert "hf_token" in SECRET_NAMES
    set_secret("hf_token", "hf_x")
    seen = {}

    class FakeST:
        def __init__(self, model, device=None, token=None):
            seen.update(model=model, device=device, token=token)

        def encode(self, texts, convert_to_numpy=True):
            import numpy as np
            return np.zeros((len(texts), 2))

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeST))
    from quilate.knowledge.embed import Embedder
    assert Embedder().encode(["a"]) == [[0.0, 0.0]]
    assert seen == {"model": "google/embeddinggemma-300m", "device": "mps", "token": "hf_x"}
