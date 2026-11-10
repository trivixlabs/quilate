"""Compara Whisper (mlx) e Parakeet (parakeet-mlx, opcional) em áudios locais.

Uso: uv run python scripts/bench_transcribe.py audio1.ogg audio2.ogg ...
Saída: tabela de tempo por minuto de áudio e transcrições em ~/quilate-dados/bench/.
"""
import argparse
import subprocess
import time
from pathlib import Path

OUT = Path("~/quilate-dados/bench").expanduser()


def duration_min(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip()) / 60


def whisper(path: Path) -> str:
    from quilate.media.transcribe import transcribe
    return " ".join(s.text for s in transcribe(path))


def parakeet(path: Path) -> str:
    from parakeet_mlx import from_pretrained
    return from_pretrained("mlx-community/parakeet-tdt-0.6b-v3").transcribe(str(path)).text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audios", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    engines = {"whisper": whisper}
    try:
        import parakeet_mlx  # noqa: F401
        engines["parakeet"] = parakeet
    except ImportError:
        print("parakeet-mlx ausente: rode `uv pip install parakeet-mlx` para incluí-lo (fora das dependências do projeto).")
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{'audio':<30}{'min':>7}" + "".join(f"{n + ' s/min':>16}" for n in engines))
    for audio in args.audios:
        mins = duration_min(audio)
        cells = []
        for name, fn in engines.items():
            t0 = time.perf_counter()
            text = fn(audio)
            cells.append((time.perf_counter() - t0) / mins)
            (args.out / f"{audio.stem}.{name}.txt").write_text(text, encoding="utf-8")
        print(f"{audio.name:<30}{mins:>7.2f}" + "".join(f"{c:>16.2f}" for c in cells))


if __name__ == "__main__":
    main()
