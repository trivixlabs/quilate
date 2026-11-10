#!/usr/bin/env python3
"""Trava de termos proibidos: impede que nomes privados entrem no repositório público."""
import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

DEFAULT_TERMS = Path(__file__).resolve().parents[2] / "quilate-interno" / "termos-proibidos.txt"


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return " ".join(plain.split())  # espaço duplo, tab ou quebra de linha não separa um termo de duas palavras


def load_terms(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    terms = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(normalize(line))
    return terms


def _has(term: str, norm: str) -> bool:
    if term.isdigit():  # número só casa inteiro: sem letra nem dígito colado (hash do uv.lock não conta)
        return re.search(rf"(?<![^\W_]){term}(?![^\W_])", norm) is not None
    return term in norm


def find_terms(text: str, terms: list[str]) -> list[str]:
    norm = normalize(text)
    return [t for t in terms if _has(t, norm)]


def scan(paths: list[Path], terms: list[str], root: Path | None = None, read=None) -> dict[str, list[str]]:
    """Com `root`, o nome checado e a chave do resultado são relativos a ele.
    `read` troca a leitura do disco (usado para ler o índice do Git)."""
    hits: dict[str, list[str]] = {}
    for p in paths:
        name = str(p.relative_to(root)) if root else str(p)
        if read is None and not p.is_file():
            continue
        found = find_terms(name, terms)
        data = read(p) if read else p.read_bytes()
        if b"\0" not in data[:8192]:
            found += [t for t in find_terms(data.decode("utf-8", "replace"), terms) if t not in found]
        if found:
            hits[name] = found
    return hits


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, check=True).stdout.decode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="todos os arquivos versionados")
    mode.add_argument("--staged", action="store_true", help="arquivos no índice")
    mode.add_argument("--message", metavar="ARQUIVO", help="mensagem de commit")
    ap.add_argument("--terms", type=Path, default=DEFAULT_TERMS)
    args = ap.parse_args()

    terms = load_terms(args.terms)
    if terms is None:
        print(f"Aviso: lista de termos não encontrada em {args.terms}. Nada foi checado.", file=sys.stderr)
        return 0

    if args.message:
        found = find_terms(Path(args.message).read_text(encoding="utf-8"), terms)
        hits = {"mensagem do commit": found} if found else {}
    else:
        root = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
        if args.all:
            names = _git(root, "ls-files").splitlines()
            hits = scan([root / n for n in names], terms, root=root)
        else:
            names = _git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
            index = lambda p: subprocess.run(
                ["git", "show", f":{p.relative_to(root)}"], cwd=root, capture_output=True, check=True
            ).stdout
            hits = scan([root / n for n in names], terms, root=root, read=index)

    for path, found in hits.items():
        for t in found:
            print(f"{path}: {t}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
