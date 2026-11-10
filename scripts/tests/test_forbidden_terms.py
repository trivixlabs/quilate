import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "forbidden_terms.py"
spec = importlib.util.spec_from_file_location("forbidden_terms", SCRIPT)
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)

def test_normalize_ignores_case_and_accents():
    assert ft.normalize("AÇÃO Imediata") == "acao imediata"

def test_find_terms_reports_each_term_once():
    assert ft.find_terms("Fulano e fulano, grupo ÁGUIA", ["fulano", "aguia", "outro"]) == ["fulano", "aguia"]

def test_digit_only_term_matches_only_as_whole_number():
    assert ft.find_terms("sha256:ab54321cd e tópico 54321", ["54321"]) == ["54321"]
    assert ft.find_terms("sha256:ab54321cd", ["54321"]) == []
    assert ft.find_terms("x154321 e 543210", ["54321"]) == []

def test_load_terms_skips_blank_and_comment_lines(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# nomes\nFulano\n\n  Águia  \n")
    assert ft.load_terms(f) == ["fulano", "aguia"]
    assert ft.load_terms(tmp_path / "nao-existe.txt") is None

def test_scan_checks_content_and_file_name_and_skips_binary(tmp_path):
    (tmp_path / "a.md").write_text("cita o Fulano")
    (tmp_path / "Fulano.tsx").write_text("limpo")
    (tmp_path / "b.png").write_bytes(b"\x89PNG\x00fulano")
    hits = ft.scan(sorted(tmp_path.iterdir()), ["fulano"])
    assert set(hits) == {str(tmp_path / "a.md"), str(tmp_path / "Fulano.tsx")}

def test_cli_without_terms_file_warns_and_passes(tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "--all", "--terms", str(tmp_path / "x.txt")], capture_output=True, text=True)
    assert r.returncode == 0 and "lista de termos" in r.stderr

def test_cli_message_mode_blocks_term(tmp_path):
    terms = tmp_path / "t.txt"
    terms.write_text("fulano\n")
    msg = tmp_path / "MSG"
    msg.write_text("feat: ajuste pedido pelo Fulano\n")
    r = subprocess.run([sys.executable, str(SCRIPT), "--message", str(msg), "--terms", str(terms)], capture_output=True, text=True)
    assert r.returncode == 1 and "fulano" in r.stdout

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

def _run(repo, terms, mode):
    return subprocess.run([sys.executable, str(SCRIPT), mode, "--terms", str(terms)], cwd=repo, capture_output=True, text=True)

def test_scan_with_root_ignores_directory_prefix(tmp_path):
    root = tmp_path / "fulano-dir"
    root.mkdir()
    (root / "a.md").write_text("limpo")
    assert ft.scan([root / "a.md"], ["fulano"], root=root) == {}
    (root / "Fulano.md").write_text("limpo")
    assert set(ft.scan([root / "Fulano.md"], ["fulano"], root=root)) == {"Fulano.md"}

def test_cli_all_ignores_repo_directory_name(tmp_path):
    repo = tmp_path / "fulano-dir"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.md").write_text("limpo")
    _git(repo, "add", "a.md")
    terms = tmp_path / "t.txt"
    terms.write_text("fulano\n")
    r = _run(repo, terms, "--all")
    assert r.returncode == 0 and r.stdout == ""

def test_cli_staged_checks_index_not_disk(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.md").write_text("cita o Fulano")
    _git(repo, "add", "a.md")
    (repo / "a.md").write_text("limpo")
    terms = tmp_path / "t.txt"
    terms.write_text("fulano\n")
    r = _run(repo, terms, "--staged")
    assert r.returncode == 1 and "a.md: fulano" in r.stdout

def test_two_word_term_matches_across_extra_spaces_and_line_breaks():
    assert ft.find_terms("o Fulano  de\tTal chegou", ["fulano de tal"]) == ["fulano de tal"]
    assert ft.find_terms("o Fulano\nde Tal chegou", ["fulano de tal"]) == ["fulano de tal"]
