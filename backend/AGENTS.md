# AGENTS.md for the backend

Python 3.12, FastAPI, APScheduler, ccxt and ccxt.pro, Telethon, Anthropic SDK, SQLite with FTS5 and sqlite-vec. Package `quilate/`, tests in `tests/`. General rules are in the root `AGENTS.md`. The architecture is in `docs/architecture.md`.

## Module map

- `cli.py`: the commands. `servir` checks the keys and starts the API and the scheduler. Without the required secrets it stays in setup mode (R47) and restarts itself when the setup page asks. `segredo` writes to the Keychain with `getpass`.
- `config.py`, `config.toml`, `config.local.toml`: settings. `load_settings()` reads the local file on top of the base. `save_local()` writes the keys of `LOCAL_KEYS` to the local file, keeping its tables and dropping comments.
- `secrets.py`: `get_secret`/`set_secret` in the Keychain. `SECRET_NAMES` is the closed list of names.
- `db.py`, `schema.sql`: connection in WAL mode, idempotent migration. Tables: `messages`, `chunks` (+ `_fts`, `_vec`), `trades`, `positions`, `candles`, `snapshots`, `verdicts`, `playbook_*`, `api_costs`, `alerts_sent`.
- `context.py`: `AppContext` with settings, connection, exchange clients, `PriceBook`, Claude client, bot and hub.
- `analyst.py`: how fixed text names the analyst (`analyst_name`, or "o analista"). Returns raw text: whoever puts it in HTML or a prompt escapes it once.
- `exchanges/`: `client.py` (ccxt, `check_read_only`), `sync.py` (balances and trades every `sync_minutes`), `cost_basis.py` (average cost), `csv_import.py` (exported history), `live.py` (live price), `symbols.py` (aliases and ambiguous tickers).
- `telegram/collector.py`: reads the group with Telethon, backfill and edits. It has no code that sends to the group. `telegram/bot.py`: Bot API in HTML, only to the owner's chat.
- `media/`: `youtube.py` (yt-dlp), `transcribe.py` (mlx-whisper), `links.py` (trafilatura), `worker.py` (`media_jobs` queue).
- `knowledge/`: `embed.py` (EmbeddingGemma), `index.py` (chunks and vectors), `search.py` (hybrid FTS5 + vector with RRF), `mentions.py` (coin cited per message).
- `market/`: `sources.py` (one client per source, fixtures in `tests/fixtures/market/`), `collect.py` (daily snapshot).
- `signals/`: `inputs.py` builds `CoinInputs`, `rubric.py` computes S1 to S7 (S7 uses the group's average polarity over 7 days: negative chatter near the high is not euphoria), `market_filter` and `rubric_verdict`. Sum 0 to 2 Manter, 3 to 4 Reduzir, 5 or more Sair. See `docs/signals.md`.
- `ai/`: `claude.py` (the only call point, cost and limit), `playbook.py` (the analyst's playbook and weekly proposals), `verdict.py` (verdict per coin with structured output).
- `cycle.py`: daily cycle and event triggers. `scheduler.py`: jobs. `track/record.py`: hits after 7, 30 and 90 days. `budget.py`: states of the monthly limit.
- `api/app.py`: routes `/api/*`, `/ws` and the frontend static files. `api/hub.py`: fan-out of ticks and events to the WebSocket. `api/setup.py`: `/api/setup/*` for the setup page (status, secrets, settings, key check, Telegram login, restart). It never returns a secret value. See `docs/api.md`.

## What the scheduler runs

`sync_all` every `sync_minutes` (default 5). `ciclo_diario` checks every 2 min whether the day's analysis arrived in the trigger topic, or whether `cutoff_hour` passed. `intradiario` every `sync_minutes`. `coleta_diaria` at 3:00. `midia` every 10 min. `conhecimento` every 30 min. `manual_semanal` on Sunday at 20:00, only if the estimate fits in the monthly limit. `historico` every hour, one batch of 2,000 messages.

## How to change things safely

- New signal or threshold: `[thresholds]` in `config.toml`, field in `Thresholds`, function in `rubric.py`, test in `test_rubric.py` with the exact limits, and the name in `frontend/src/lib/types.ts` if the dashboard shows it. Update `docs/signals.md`.
- New Claude call: only through `Claude.parse(...)` in `ai/claude.py`. It records the cost even for invalid output and raises `BudgetExceeded` at the limit. Calls above 16,000 output tokens use streaming.
- New route: in `api/app.py`, with a test in `test_api.py` using an `AppContext` without real clients. Nothing that spends money or changes the portfolio on `GET`. Update `docs/api.md`.
- New market source: client in `market/sources.py`, JSON fixture recorded from an endpoint without a key, test with `respx`.
- Schema change: `schema.sql` for a new table, `db.py` to change an existing table. Test in `test_db.py` that runs the migration twice.

## Tests

- `uv run pytest -q`. `asyncio_mode = auto`: an `async def` test runs directly.
- `conftest.py` provides `db` (SQLite in `tmp_path`, already migrated) and `memory_keyring` (Keychain in memory).
- Each file has its own fakes: `FakeAnthropic` in `test_claude.py`, `FakeTg` in `test_cli.py` and `test_collector.py`, `FakeExchange` in `test_client.py` and `test_sync.py`. Copy the pattern, do not build a mock layer.
- `load_settings()` without a path, in a test, reads only the versioned `config.toml`. Before collection, `conftest.py` points `DEFAULT_PATH` to a copy with no `config.local.toml` next to it. For group values use `replace(settings, ...)`, never the local file.
- The test embedder is fake. No test downloads a model or touches the network.

## Pitfalls on this side

- `check_read_only` runs outside the sync loop and fails closed. A network error during the check lets `servir` start: this is a parked finding, do not "fix" it without a decision.
- `cost_basis` converts fees paid in BNB to USD. A fee in a coin other than the quote coin is assumed to be in the quote coin on MEXC and Bybit. Confirm with the real CSV.
- The CSV row id is a hash of the content plus an occurrence counter. Changing the header changes the ids and duplicates trades.
- `media/youtube.py` uses the Python API of `yt_dlp`, not the command line. Video URL and title are group data: never put them in a shell command.
- The `AFTER DELETE` trigger of `chunks` deletes the vector in `chunks_vec`. Always delete a chunk through `chunks`, never directly in `chunks_vec`.
