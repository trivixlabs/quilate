# Contributing to Quilate

[Português](CONTRIBUTING.pt-BR.md)

Thanks for your interest. Issues and pull requests are welcome, in English or Portuguese, from anyone. Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- Read the [README](README.md) and [docs/architecture.md](docs/architecture.md).
- For a bug or an idea, open an issue first with the templates. For a small fix, a pull request alone is fine.
- For a security problem, do not open a public issue. Follow [SECURITY.md](SECURITY.md).
- Never put a real key, token, password, chat ID, username or portfolio data in an issue, a commit, a test or a screenshot. Use made-up values.

## Set up

Quilate has three parts. You only need the one you change.

### Dashboard (`frontend/`)

Node 22.12 or newer.

```sh
cd frontend
npm ci
npm run dev        # http://127.0.0.1:5173, proxies /api and /ws to 127.0.0.1:8000
npm test           # vitest
npm run build      # type check and build into backend/quilate/api/static
```

Open <http://127.0.0.1:5173/?demo=1> to work with fake data and no backend.

### Backend (`backend/`)

A Mac with Apple Silicon, [uv](https://docs.astral.sh/uv/) and the Homebrew Python 3.12. The Python that uv downloads by itself cannot load `sqlite-vec`.

```sh
brew install python@3.12
cd backend
uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"
uv run pytest -q                      # no network, no Keychain, no model download
uv run pytest -q ../scripts/tests
uv run ruff check . ../scripts
```

The tests need no secret. To run the real system, see [docs/install.md](docs/install.md).

### Notch app (`notch/`)

macOS 15 or newer and Swift 6 (Xcode or the Command Line Tools).

```sh
cd notch
swift test
./build.sh && open Quilate.app
./demo.sh          # fake backend on 127.0.0.1:8000
```

## Workflow

1. Fork the repository and create a branch from `main`.
2. Write a failing test first, then the smallest code that makes it pass.
3. Run the tests of the side you changed.
4. Open a pull request against `main` and fill in the template.

Each pull request needs:

- The `ci-ok` check green. CI runs only the jobs for the folders you changed, plus a secret scan.
- An approval from one of the two maintainers.
- Tests for new behavior.
- No secret and no personal data.
- Docs updated when you change behavior, a setting or an API field. If you change a field of `/api/overview`, `/api/verdicts` or `/api/costs`, update the notch app in the same pull request ([docs/api.md](docs/api.md)).

Pull requests are merged with squash or rebase. We do not merge these changes:

- code that places orders or moves funds
- code that writes to a Telegram group
- a server that listens beyond `127.0.0.1`
- an AI call that skips `backend/quilate/ai/claude.py`

[AGENTS.md](AGENTS.md) has the full list of fixed rules.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/), in English or Portuguese:

```
feat: add Kraken read-only sync
fix: corrige preço médio com taxa em BNB
docs: explain trigger_topic
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `ci`, `chore`. One change per commit. Subject up to 72 characters, without a final period.

An aside, not a rule: a commit called "fixes" at 23:59 on a Friday does not count as a message.

## Code style

- Identifiers in English. The existing UI text, CLI commands, comments and docstrings are in Portuguese. New comments can be in English or Portuguese. User-facing text stays in Portuguese until the interface is translated.
- Python: type hints on public functions, `frozen=True` dataclasses for settings and results, `ruff` clean.
- TypeScript: strict mode, one component per file with its test next to it.
- New dependency only when the standard library and the installed packages cannot do it. Versions are locked in `uv.lock` and `package-lock.json`.

The per-side rules are in [backend/AGENTS.md](backend/AGENTS.md), [frontend/AGENTS.md](frontend/AGENTS.md) and [notch/AGENTS.md](notch/AGENTS.md).

## Optional: the leak check hook

```sh
scripts/install-hooks.sh
```

This installs a `pre-commit` and a `commit-msg` hook that run `scripts/forbidden_terms.py`. The script looks for private terms from a list that only the maintainers have, in a separate private repository. Without that list, it prints a warning and lets the commit through, so the hook does nothing for most contributors.

## Getting help

Open an issue with the "Idea" template, or comment on the issue you are working on. There is no chat channel yet.

Every contribution is licensed under the [AGPL-3.0-or-later](LICENSE), the same license as the project. There is no separate contributor agreement.
