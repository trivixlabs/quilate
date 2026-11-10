# Verification

This page lists what proves that Quilate works, what was checked without real accounts, and what still needs real data. Version 1 was checked on 2026-11-04. The numbers in section 1 were refreshed on 2026-11-10.

Summary: the tests and the build pass, and no secret is in the project. Of the 8 "done" criteria of the design, 1 is verified without real accounts. The other 7 need real keys, the Telegram login and real data. Only the owner of an installation can run them. Agents never see or type a secret.

## 1. Tests and build

```sh
(cd backend && uv run pytest -q && uv run pytest -q ../scripts/tests && uv run ruff check . && uv run ruff check ../scripts)
(cd frontend && npm test && npm run build)
(cd notch && swift test)
```

Result on 2026-11-10:

```
383 passed in 9.13s
11 passed in 0.28s
All checks passed!
All checks passed!

 Test Files  12 passed (12)
      Tests  66 passed (66)
✓ built in 141ms

Test run with 10 tests in 0 suites passed
```

The charts and animation libraries are split into their own chunks, so the build has no chunk above 500 kB.

## 2. Secrets in the project

```sh
git ls-files | xargs grep -nE "(sk-ant-|api_hash|BEGIN .*PRIVATE)"
```

On 2026-11-10 the hits are the secret name `api_hash` (the Keychain name), fake test values such as `"h"` or `"abc"`, and this pattern quoted in `docs/`. The only `sk-ant-` is the fake value `sk-ant-valor-secreto` in `frontend/src/pages/Configuracao.test.tsx`, which checks that a typed key leaves the page. No real key and no private key in any file.

```sh
ls -a . | grep -E "\.session|\.env"
git ls-files | grep -E "\.session|\.env|\.(sqlite|sqlite3|db)$"
```

Both outputs were empty. No `.session`, `.env` or SQLite file exists in the folder or in Git. CI also runs gitleaks over the whole history on every pull request.

## 3. Proofs without secrets

`uv run quilate --help` lists 7 commands: `segredo`, `telegram-login`, `checar-chaves`, `importar`, `manual-inicial`, `ciclo`, `servir`.

`uv run quilate servir --host 0.0.0.0` prints `Recusado: o servidor só escuta em 127.0.0.1.` and exits with code 1.

`http://127.0.0.1:5173/?demo=1` (with `npm run dev`) shows every page with fake data. The production bundle has no "Dados de demonstração" string.

`notch/demo.sh` serves the notch fixtures on `127.0.0.1:8000`. With the port in use, it prints `Port 8000 is in use. Stop the Quilate backend first.` and exits with code 1.

## 4. Installation

Follow [install.md](install.md). The commands below run inside `backend/`.

| Step | Command | Expected |
|---|---|---|
| 1 | `uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"` | Dependencies installed without error. |
| 2 | `uv run quilate segredo <name>` for each secret | Asks for the value without echo and confirms it was saved in the Keychain. |
| 3 | `uv run quilate telegram-login` | Asks for phone, code and two-step password. Ends without error. No `.session` file appears on disk. |
| 4 | `uv run quilate checar-chaves` | No key with trading or withdrawal. Binance and Bybit report permissions through the API. MEXC and Gate need the owner's confirmation. |
| 5 | `uv run quilate importar --meses 12` | Ends without error and reports the number of messages imported. |
| 6 | `uv run quilate manual-inicial` | Shows the estimate in USD and asks for `s`. Any other answer cancels with no cost. |
| 7 | `uv run quilate servir` | Checks the keys and starts the dashboard on `http://127.0.0.1:8000`. Refuses to start with a key that allows trading or withdrawal. |

Before step 5, accept the license of `google/embeddinggemma-300m` on Hugging Face and save a read token with `uv run quilate segredo hf_token`. Without it, indexing fails.

## 5. "Done" criteria

| # | Criterion | Status |
|---|---|---|
| 1 | 4 exchanges sync balances, and the live price reaches the screen | Needs real data |
| 2 | Each coin above the dust limit has an average cost or the "custo desconhecido" warning | Needs real data |
| 3 | 12 months of the group in the database, with screenshots, audio and live streams | Needs real data |
| 4 | The analyst's playbook as a draft, reviewable on the dashboard | Needs real data |
| 5 | The full daily cycle runs by itself | Needs real data |
| 6 | The 3 triggers outside the cycle create alerts | Needs real data |
| 7 | Monthly spending on the dashboard, and the cut at the limit | Needs real data |
| 8 | No secret in any file of the project folder | Verified (sections 2 and 3). Tests also cover the Keychain in memory. |

### Criterion 1: exchanges and live price

Save the 8 read-only key values (`binance_key`, `binance_secret`, `mexc_key`, `mexc_secret`, `bybit_key`, `bybit_secret`, `gate_key`, `gate_secret`), then run `uv run quilate checar-chaves` and `uv run quilate servir`.

Proof: `checar-chaves` reports no key with trading or withdrawal, and the "Carteira" page shows balances from the 4 exchanges. The MEXC price arrives by polling: check that it changes on screen without a reload. Binance, Bybit and Gate prices arrive by WebSocket.

### Criterion 2: average cost

Import the CSV of each exchange. Before that, compare the header expected by each of the 4 CSV readers with the real export file. Proof: each coin above `dust_usd` on the "Carteira" page shows an average cost or the "custo desconhecido" warning. For coins with the warning, use the manual cost override.

### Criterion 3: 12 months of history

Run `uv run quilate telegram-login` and `uv run quilate importar --meses 12`. Proof: the command ends without error, and the dashboard shows messages from the last 12 months, with text from screenshots and transcripts of audio and live streams.

Transcriber choice: run `uv run python scripts/bench_transcribe.py a1.ogg ... a10.ogg` with 10 audio files from the analyst. The script prints the time per minute of audio and writes the transcripts to `~/quilate-dados/bench/`. Read them and choose between Whisper and Parakeet.

### Criterion 4: the analyst's playbook

Run `uv run quilate manual-inicial`. It shows the estimate in USD and asks for `s`. Proof: after `s`, the "Manual do analista" page shows the playbook as a draft. Each rule has an approve button. The page does not edit the text of the playbook or of the rules. When every rule is approved, the playbook becomes approved. If the command stops in the middle, run it again: parts already extracted are saved and not paid twice.

### Criterion 5: daily cycle

Run `uv run quilate ciclo`. In a manual run, the output goes to the terminal. The log file `~/quilate-dados/logs/quilate.log` exists only when `servir` runs through the LaunchAgent (`sh ops/instalar-launchd.sh`).

Four proofs:

1. Signals: open a coin from the home page. It shows the 7 signals with name, value and alert. `curl -s http://127.0.0.1:8000/api/coins/BTC` returns the same list in `signals`, with 7 items.
2. Verdict: the home page shows one verdict per coin above the dust limit, with today's date. Also check `sqlite3 ~/quilate-dados/quilate.sqlite "SELECT symbol, trigger, final_verdict FROM verdicts WHERE day=date('now','localtime') AND trigger='diario'"`.
3. Hit record: the "Histórico de acertos" page (`GET /api/track`) lists the recorded verdicts.
4. Bot summary: the Telegram bot sends the daily summary to the chat in `telegram_chat_id`.

To prove it runs by itself, leave `servir` running and repeat the four proofs the next day, without running `ciclo` by hand.

Also check what the data APIs return on the first real call:

- The unit of the Coinalyze funding. The "Mercado" page shows it as a percentage. Compare with the Coinalyze site.
- The ETF flow URL. If the "Mercado" page shows no data for ETF flows, the URL is wrong.

### Criterion 6: triggers outside the cycle

Each trigger recomputes a coin outside the daily cycle and writes a row in `verdicts` with `trigger` set. The bot sends a message only if the final verdict changed. A failed recompute shows `recálculo de <SYM> (<trigger>) falhou` in the terminal or the log.

```sh
sqlite3 ~/quilate-dados/quilate.sqlite "SELECT day, symbol, trigger, final_verdict FROM verdicts WHERE trigger<>'diario' ORDER BY id DESC"
```

| Trigger | What fires it | How to observe |
|---|---|---|
| `analista` | A message from the analyst that cites a coin you hold. Recomputed with Claude. | A row with `trigger='analista'`. If the verdict changed, the bot sends "<name> falou de <SYM>." with the change. |
| `tag` | A new Binance Monitoring Tag, or a coin that left an exchange. Rubric only. | A row with `trigger='tag'`. If it changed, the bot says the coin got the Monitoring Tag or left an exchange. |
| `movimento` | Live price more than `intraday_move` away from yesterday's close. Rubric only, at most once per day per coin. | A row with `trigger='movimento'`. If it changed, the bot says the coin went up or down X% since yesterday's close. |

The default `intraday_move = 0.10` is 10% from the previous day's close. If the market does not create the event, wait for a day with a strong move, or test with simulated data.

### Criterion 7: spending and limit

Proof: the month's spending shows on the dashboard after the first cycle. The limit is `budget_usd` (default 50). The automated tests cover the alert at `budget_alert_ratio` (80%) and the block at 100%. This was not checked against a real Anthropic account.

## 6. Open checks

- [x] Build without a chunk above 500 kB.
- [ ] The header of each of the 4 CSV readers checked against a real export.
- [ ] The Coinalyze funding unit checked on the first real call.
- [ ] The ETF flow URL confirmed.
- [ ] The MEXC price arrives by polling.
- [ ] `bench_transcribe.py` run with 10 audio files from the analyst, and the choice made between Whisper and Parakeet.
- [ ] The EmbeddingGemma license accepted on Hugging Face.
- [ ] MEXC and Gate checked on the exchange site as read-only and listed in `confirmed_read_only`.
- [ ] The BNB fee column in the Binance CSV checked (today it becomes zero).
- [x] The Claude price table in `config.toml` checked against the official page on 2026-11-09 (R45).
- [x] The Hugging Face token goes to the Keychain (`quilate segredo hf_token`). Nothing in `~/.cache/huggingface/token`.
- [ ] CI passes on GitHub Actions in `trivixlabs/quilate`, with the backend on macOS and the Homebrew Python. It passed in the earlier private repository. On 2026-11-10 it had not run in this one yet.
