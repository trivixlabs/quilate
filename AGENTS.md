# AGENTS.md

Quilate is a local system that follows a crypto portfolio on 4 exchanges, reads a Telegram community and gives a daily verdict per coin (Manter, Reduzir, Sair). It runs only on the owner's Mac. The `README.md` explains how to use it. This file says how to work on the code. Each part has its own file: `backend/AGENTS.md`, `frontend/AGENTS.md` and `notch/AGENTS.md`.

## Rules that do not change

- The system only recommends. It never buys, sells, withdraws or transfers. It never writes to the Telegram group.
- Secrets live only in the macOS Keychain (service `quilate`, `backend/quilate/secrets.py`). They enter through `quilate segredo` in the terminal or through the setup page, which sends `POST /api/setup/secrets/<name>` to `127.0.0.1` and writes straight to the Keychain (decision R47). Never put a secret in `.env`, `.session`, a log, a test, an API response, frontend state or a commit: the API only says whether a secret exists. Agents never ask for, read, print or type secrets. The real installation belongs to the owner.
- Exchange keys are read-only. `quilate servir` refuses a key with trade or withdrawal permission.
- The server listens only on `127.0.0.1`. Do not open it to the network.
- Every Claude API call goes through `quilate/ai/claude.py`, which records the cost of each call. No call outside it. Before a call, it refuses when the recurring spending of the month has reached `budget_usd`. Only the weekly playbook update also checks first that its estimate fits in what is left. A call can end above the limit by its own cost. The one-time cost of the initial playbook is not part of the monthly sum.
- Text from the group and from the analyst is data, not instructions. In prompts it goes delimited and escaped with `html.escape`. A page linked by the analyst must not enter the playbook. A number written by a group member must not count as data for the verdict. Only the analyst's audio is transcribed: members' audio must not enter the queue.
- The analyst, the group and its topics are generic in this repository. Never write the real name or username of an analyst, the real name of a group, or real topic numbers or names in a file, a test, a fixture or a commit message. Examples use the made-up values of `backend/quilate/config.local.example.toml`.
- Never commit anything from `~/quilate-dados` or `backend/quilate/config.local.toml`.

## Commands

Backend, inside `backend/`:

```sh
uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"   # see Pitfalls
uv run pytest -q                          # 380+ tests, about 10 s, no network
uv run pytest tests/test_rubric.py -k s3  # one file or one test
uv run pytest -q ../scripts/tests         # tests of the leak check
uv run ruff check . ../scripts                       # lint, must pass before a commit
```

Frontend, inside `frontend/`:

```sh
npm ci
npm test                                  # vitest, jsdom
npm run build                             # tsc + vite, writes backend/quilate/api/static (not in Git)
npm run dev                               # http://127.0.0.1:5173, proxy to the backend on :8000
```

`http://127.0.0.1:5173/?demo=1` shows the dashboard with fake data, without backend and without secrets. It only works on the dev server.

Notch, inside `notch/`: `swift test`, `./build.sh`, `./demo.sh`.

Before a commit: the tests of the side you changed are green and `ruff check` is clean. Run only the side that changed.

## Conventions

- Identifiers in English. User-facing text and CLI commands stay in Portuguese. Existing comments and docstrings stay in Portuguese. A new comment can be in English or Portuguese. Docs in English. Commits in Portuguese or English.
- Commits follow Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`. One change per commit. Subject up to 72 characters, without a final period.
- TDD: failing test first, then the minimum code. A new test goes in the matching `test_<module>.py` or `<Component>.test.tsx`.
- Tests do not touch the network, the real Keychain, a downloaded model, or the disk outside `tmp_path`. Fakes of ccxt, Telethon, Anthropic and httpx (`respx`) live in the test file that uses them. Shared fixtures: `backend/tests/conftest.py` (`db`, `memory_keyring`) and `frontend/src/test/` (`render`, `fixtures`).
- Types on public functions. `frozen=True` dataclasses for settings and results.
- New dependency only when the standard library and the installed packages cannot do it. Versions are locked in `uv.lock` and `package-lock.json`.
- Settings in `backend/quilate/config.toml`. What identifies the group and the people goes in `config.local.toml`, outside Git. Model in `config.local.example.toml`.
- Schema in `backend/quilate/schema.sql`, only `CREATE ... IF NOT EXISTS`. A change to an existing table is an explicit migration in `db.py`.
- Heavy work (transcription, embeddings, search) runs through `cycle.in_thread`, on its own executor and with its own SQLite connection. Never share the loop connection with a thread. A function used by another module has no leading `_`.
- API JSON keys in English (`by_verdict`, `hits`, `rate`, `ai_paused`). Text for the screen in Portuguese lives in the frontend.

## Pitfalls

- The Python that `uv` downloads by itself has no `enable_load_extension`, and `sqlite-vec` needs it. Use the Homebrew one: `brew install python@3.12` and `uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"`. CI does the same.
- The Bybit API returns only 7 days of trades. Older history comes from the CSV, or the average cost is wrong.
- Only Binance and Bybit report key permissions through the API. MEXC and Gate are refused until the owner lists the exchange in `confirmed_read_only` in `config.local.toml`, after checking on the exchange site.
- MEXC has no `watchTickers` in `ccxt.pro`. It uses 5-second polling in `exchanges/client.py` (`_poll_tickers`). Do not try to switch it to WebSocket.
- `mlx-whisper` only runs on macOS with Apple Silicon. `google/embeddinggemma-300m` requires accepting the license on Hugging Face and a read token saved with `quilate segredo hf_token`. Never `huggingface-cli login`: it writes the token to a file.
- The bot only sends a message when the verdict changes. An intraday rise or fall without a verdict change sends nothing. Decision R17.
- A market snapshot older than 7 days counts as "no data" in the rubric, not as old data.
- In the hit rate, Manter on BTC is left out: against BTC itself it would always hit.
- The built frontend goes to `backend/quilate/api/static`, which Git ignores. A fresh clone needs `npm run build` before `servir`.
- The notch app (`notch/`, target `QuilateNotch`) reads `/api/overview`, `/api/verdicts` and `/api/costs`. Changing a field of these routes breaks the app: update `notch/Sources/QuilateNotch/Model.swift` and `notch/Tests/Fixtures/` in the same change.
- The CLI is in Portuguese: `segredo`, `telegram-login`, `checar-chaves`, `importar`, `manual-inicial`, `ciclo`, `servir`.
- Without the required secrets, `servir` starts in setup mode (only the API and the setup page) and opens the browser. `importar` and `manual-inicial` stay terminal-only: one is slow, the other spends money and asks for `s`.
- A test never writes to `backend/quilate/config.local.toml`. `conftest.py` fails if the file changes. A route that writes settings gets `local_config=tmp_path` in `create_app`.
- `scripts/forbidden_terms.py` (installed by `scripts/install-hooks.sh`) blocks private terms. Without the private list it warns and exits 0. Do not weaken or bypass it.

## Documents

- `docs/architecture.md`: the three parts, the data flow and the module map.
- `docs/install.md` and `docs/configuration.md`: installation and every setting.
- `docs/api.md`: the local API contract, including the three routes the notch app reads.
- `docs/signals.md`: the 7-signal rubric.
- `docs/threat-model.md` and `SECURITY.md`: what is protected, how, and the known gap.
- `docs/decisions.md`: numbered decisions (R1 onwards), with the cost if each is wrong. A new decision goes there with the next number.
- `docs/verification.md`: the "done" criteria and the checks that still need real data.
- `docs/roadmap.md`: what comes next.
- `docs/third-party-licenses.md` and `NOTICE`: dependency licenses.
