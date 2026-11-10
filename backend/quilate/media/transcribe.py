from dataclasses import dataclass
from pathlib import Path

MODEL = "mlx-community/whisper-large-v3-turbo"


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def transcribe(path: Path) -> list[Segment]:
    import mlx_whisper

    out = mlx_whisper.transcribe(str(path), path_or_hf_repo=MODEL, language="pt")
    return [Segment(s["start"], s["end"], s["text"].strip()) for s in out["segments"] if s["text"].strip()]
