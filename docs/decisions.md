# Decisions

Numbered decisions taken while building version 1, outside the original design. Each one says what was decided, why, and the cost if it is wrong. New decisions go at the end, with the next number.

This is a log. Some entries describe a state that later changed. When an entry and the code disagree, the code is right. Names of settings are the current ones.

## Version 1 build

- **R1.** Version 1 was built on one branch in the same repository, without a worktree. Fresh repository, no parallel work. Cost if wrong: none, the branch was isolated.
- **R2.** Python is pinned to 3.12 through uv (`requires-python = ">=3.12,<3.13"`). The system had 3.14, and the torch and mlx wheels lag behind. Cost if wrong: a later version bump.
- **R3.** The market snapshot also stores the key `cg_assets` (CoinGecko top 250). The mention extractor builds its coin names from it. It filled a gap in the plan. Cost if wrong: a small refactor.
- **R4.** Transcript chunking: a segment joins the current block when it starts less than 60 s after the block start. Cost if wrong: chunk sizes only.
- **R5.** The CSV readers follow the documented export header of each exchange, tested with synthetic files. They must be checked against a real export. The owner was not available during the build. Cost if wrong: one parser fix per exchange.
- **R6.** The transcription benchmark script (`backend/scripts/bench_transcribe.py`) is built and unit-checked. The real run, and the choice between Whisper and Parakeet, are left to the owner: they need real audio and judgment. Cost if wrong: none, the default is `mlx-whisper`.
- **R7.** Tests do not download EmbeddingGemma. They use a fake embedder. The docs explain the Hugging Face license step. Cost if wrong: none.
- **R8.** Market fixtures: real responses were captured only from public endpoints without a key. For sources with a key (Coinalyze, FRED, CoinGecko Demo), the fixtures follow the documented response shape. Agents never have secrets. Cost if wrong: a parser fix on the first real call.
- **R9.** The real installation with the owner's secrets is a stop point for agents. It is security-sensitive, and agents never handle secrets. Cost if wrong: none.
- **R10.** Telegram backfill re-scans the recent window (`refresh_days = 2`) and continues the history backwards from the oldest stored message. Hourly batches use `max_messages`. The plan text and the plan test disagreed. Cost if wrong: one extra scan per hour.
- **R11.** Audio jobs only for the analyst. Members' audio messages are stored as rows (`media_kind = audio`) but not downloaded. The design says the group is only sentiment. Cost if wrong: members' spoken opinions are missing from S7.
- **R12.** The analyst's photos without a caption go to the model, with every known coin as a candidate. The output is filtered to known coins. The design says the AI reads the analyst's screenshots. Cost if wrong: a few extra Haiku calls (cents).
- **R13.** The ETF flow URL is not verified and stays as it is. ETF flows only feed the Market page, never a signal. A failure lands in `CollectReport.failed`. Cost if wrong: an empty ETF card until the URL is fixed.
- **R14.** `current_playbook` returns `Playbook | None`. `None` (no version yet) is treated as an empty, unreviewed playbook. The planned signature had no empty case. Cost if wrong: one `None` check.
- **R15.** Without a `delisting` snapshot, `listed_on = 0` (unknown), so S5 can only alert on a Monitoring Tag. It is never derived from your holdings: the number of exchanges where you hold a coin is not the number where it is listed, and it would raise false Sair signals. Cost if wrong: S5 is silent until the snapshot exists.
- **R16.** Media processing and indexing run in a thread with their own SQLite connection. The loop connection is never shared across threads. Whisper and embeddings would freeze the loop, and their rollback could drop other writes. Cost if wrong: one extra connection.
- **R17.** Price-move and Monitoring Tag triggers send an alert only when the final verdict changes ("if the verdict changes, the bot warns"). This overrides a planned test that alerted on any move above 10%. Cost if wrong: the owner misses a ping about a big move that did not change the verdict.
- **R18.** `alerts` on a card is a count of signals in alert ("x de 7" on the UI). The codes stay in `signals`. Cost if wrong: trivial.
- **R19.** The `usdbrl` snapshot comes from the FRED series `DEXBZUS` in the daily collection. No source wrote it before. There is no hardcoded rate. Cost if wrong: `total_brl` stays null without a FRED key.
- **R20.** A card's price has no source or date field. The "source and date on every number" rule applies to the Market page. Live card prices come from the exchanges. Cost if wrong: one extra field later.
- **R21.** A Telegram outage must not end `servir`. It reconnects with backoff from 1 s to 300 s. The LaunchAgent has no `KeepAlive`: a Mac that boots before Wi-Fi is the normal case. Cost if wrong: more code in `cli.py`.
- **R22.** The history floor is fixed at 2015-01-01. Telegram reports the member's join date as the channel date, so that date cannot be used. Cost if wrong: one empty Telegram call per hour after the start is reached.
- **R23.** The dashboard has a demo mode (`?demo=1`, dev server only) with the test fixtures and fake ticks. It lets anyone check the UI without secrets. Cost if wrong: a small dev-only module.
- **R24.** The production bundle has no "Dados de demonstração" string. The Coinalyze funding value is stored raw. Its unit stays unconfirmed until the first real call, and it is listed as a check for the owner. Cost if wrong: funding shown 100 times off on the Market page only. No signal uses it.
- **R25.** The secret scan finds the variable name `api_hash` and fake test values. They are not secrets: the scan's regular expression matches the name. No `sk-ant-` and no private key was found. Cost if wrong: none.

### Parked at the end of version 1

- The first Bybit sync reads only the last 7 days of trades (API window). Older trades must come from the Bybit CSV. Deferred and documented. Cost: wrong average cost on Bybit coins until the CSV is imported.
- A network error while checking key permissions logs `falha ao verificar`, and `servir` still starts. This is fail-open on the check, not on unsafe keys. Deferred: the system never sends orders, and an unsafe key found later stops it. Cost: a trade-enabled key runs until the next successful check.
- MEXC history is assumed to start 30 days back when no `startTime` is given. Not verified. Deferred to the first real run. The CSV covers older history.

## Full review before real keys and before GitHub

The review found 0 critical, 4 high, 7 medium and 13 low issues. No secret in files, history, API or frontend.

- **R26.** MEXC and Gate keys cannot be checked through the API. Quilate refuses them until the owner checks on the exchange site and lists the exchange in `confirmed_read_only` in `config.local.toml`. Cost if wrong: one more setting during installation.
- **R27.** The same trade from the API and from the CSV counts once. Two trades are equal when exchange, symbol, side, time rounded to the second and quantity match. Cost if wrong: two real identical trades in the same second become one.
- **R28.** Sync fetches trades also for coins that had a position and for coins that already have a stored trade, not only for the current balance. Cost if wrong: more API calls every 5 minutes.
- **R29.** The weekly playbook draft shows up for approval even when an approved version exists. Verdicts keep using only the approved version. Cost if wrong: none.
- **R30.** If there is no market snapshot for the day, the daily cycle collects it before running. This covers a Mac that sleeps at 3:00. Cost if wrong: one repeated collection.
- **R31.** Links from the analyst to local network, loopback or link-local addresses are not fetched. Cost if wrong: none.
- **R32.** The httpx log filter at WARNING lives in `cli.main`, not in a module import. Cost if wrong: none.
- **R33.** The analyst's username leaves the versioned `config.toml` and goes to `config.local.toml`, outside Git. Tests use a made-up value. Cost if wrong: none.
- **R34.** S3 goes back to the design: 30-day average volume divided by the 180-day average, with 180 candles or more. The code had 7 over 30 without a record. Cost if wrong: none, `CANDLE_DAYS = 400` already covers it.
- **R35.** Exchange sync runs under an `asyncio.Lock`. The 5-minute job and the daily cycle never sync at the same time. Cost if wrong: none.
- **Parked B2.** A fee paid in BNB in the Binance CSV becomes zero, with a log warning on each line. The real CSV is needed to know the column. Cost: the CSV average cost is a little below the real one.

## Second round on the parked items

- **R36.** Pages linked by the analyst stay out of the playbook. The playbook goes into the system prompt of every verdict, and a linked page is third-party text. Link chunks stay in search and on the dashboard. The text of the playbook sources is escaped with `html.escape`, as in the verdict. Cost if wrong: a rule that appears only on a linked page does not enter the playbook.
- **R37.** A number written by a group member does not count as a data number when the verdict is validated. Only the playbook, the signals, the coin data and the market count. Cost if wrong: the verdict cannot quote a price that appeared only in a group message.
- **R38.** S7 uses the average polarity of the group's mentions over 7 days. Euphoria needs positive polarity near the high. Lack of interest does not depend on polarity. Without polarity data, the old rule applies. This gives the Haiku extraction a use. Cost if wrong: euphoria with negative chatter no longer alerts.
- **R39.** The weekly playbook update calls Opus only if the estimate fits in what is left of the monthly limit. Otherwise it waits, with a log warning. Cost if wrong: one week without an update proposal.
- **R40.** The Hugging Face token goes to the Keychain as `hf_token` and is passed to `SentenceTransformer`. No `huggingface-cli login`. Cost if wrong: none.
- **R41.** Analyst links are fetched with `httpx` without following redirects automatically. The host is resolved before each hop, and every IP must be public. A DNS answer that changes between the check and the connection is still possible. Cost if wrong: a page behind more than 5 redirects is not fetched.
- **R42.** Heavy work runs on its own executor (`cycle._HEAVY`). On `SIGTERM`, `servir` closes what it owns and exits with `os._exit` if a transcription is still running, instead of waiting 20 s for `launchd`. The job comes back as pending. Cost if wrong: none.
- **R43.** API JSON keys are in English (`by_verdict`, `by_signal`, `hits`, `rate`, `outcomes`, `hit`, `verdicts`, `ai_paused`, `ai_failed`). Functions used by another module lose the leading `_` (`last_price`, `daily_closes`, `snapshot`, `fmt_num`). The `acertos` job, which only wrote a log line, was removed. Cost if wrong: none, no stored data used the old names.
- **R44.** CI on GitHub Actions on each push to `main`. The backend runs on macOS, because `mlx-whisper` only installs on Apple Silicon. macOS minutes cost 10 times Linux minutes: about 40 runs per month fit in the free quota of a private repository. Cost if wrong: turn the workflow off. Later change: CI also runs on pull requests, runs only the jobs whose folder changed, scans for secrets, and reports one required check, `ci-ok`. With the repository public, the private-repository quota no longer applies.
- **R45.** The Claude price table was checked on 2026-11-09 against the official pricing page. Sonnet 5.5 cache reads cost 0.10, not 0.20. Haiku 5.5 charges 5 times on everything when the request prompt is above 100,000 tokens, counting cache reads and writes. `ModelPrice` got `long_prompt_tokens` and `long_prompt_mult`, and `cost_usd` applies the tier. Cost if wrong: spending counted too high or too low until the next check.
- **R46.** Mentions escape `<` and `>` with `html.escape`, as the verdict and the playbook do. A member can no longer write `<dados msg_id=...>` and steer the polarity of another message in the batch. Cost if wrong: Haiku reads `&lt;` instead of `<` in messages with a less-than sign.

## Setup page

- **R47.** A secret can enter through the setup page of the dashboard, besides `quilate segredo` in the terminal. The value travels once, in `POST /api/setup/secrets/<name>`, only on `127.0.0.1` and behind the Host and Origin checks of `LocalOnly`. The backend writes it straight to the Keychain, never returns it, never logs it, and the API only says whether each secret exists. The field is `type="password"` with `autocomplete="off"`, and it is cleared after saving. Without the six required secrets (`anthropic_api_key`, `telegram_api_id`, `telegram_api_hash`, `telegram_group_id`, `telegram_bot_token`, `telegram_chat_id`) or without `analyst_username`, `servir` starts in setup mode: only the API and the page, with no exchange, scheduler or Telegram, and it opens the browser on `/configuracao`. `POST /api/setup/restart` stops uvicorn, and `main` replaces the process with the same command. Cost if wrong: the secret passes through the browser's memory and the API process during one local request. Whoever does not want this keeps using the terminal.
- **R48.** The interval of the exchange sync and of the price-move check leaves the code and becomes `sync_minutes` (1 to 60, default 5) in `config.toml`, editable on the page. The page also edits `owner_name`, `analyst_username`, `analyst_name`, `confirmed_read_only`, `budget_usd`, `budget_alert_ratio`, `dust_usd`, `cutoff_hour` and `intraday_move`, and writes them to `config.local.toml` through `save_local`. The writer keeps the file's tables but drops the comments. Cost if wrong: an interval below 5 minutes may hit the exchanges' rate limits.
- **R49.** The page stores only the owner's name (`owner_name`), for display. Tax IDs, documents and other personal data go in no file: the system does not sign up to exchanges and has no use for them. Cost if wrong: none.
