import threading

from quilate.secrets import get_secret

MODEL = "google/embeddinggemma-300m"


class Embedder:
    """EmbeddingGemma local (768 dimensões), carregado só no primeiro uso."""

    def __init__(self, device: str = "mps"):
        self.device = device
        self._model = None
        self._lock = threading.Lock()  # índice e veredito chamam de threads diferentes: carrega uma vez só

    def _load(self):
        from sentence_transformers import SentenceTransformer

        try:
            # token do Keychain: nada gravado em ~/.cache/huggingface/token
            return SentenceTransformer(MODEL, device=self.device, token=get_secret("hf_token"))
        except Exception as e:
            raise RuntimeError(
                f"Não foi possível carregar {MODEL}. O modelo exige aceitar a licença no Hugging Face "
                f"e gravar um token de leitura com `quilate segredo hf_token` antes do primeiro uso. Erro original: {e}"
            ) from e

    def encode(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            return self._model.encode(texts, convert_to_numpy=True).tolist()
