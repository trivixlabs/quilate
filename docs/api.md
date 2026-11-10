# Local API

The backend serves a JSON API and one WebSocket on `http://127.0.0.1:8000`. The dashboard uses all of it. The notch app reads three routes, marked **notch** below.

Code: `backend/quilate/api/app.py` and `backend/quilate/api/setup.py`. The frontend mirror of these shapes is `frontend/src/lib/types.ts`.

## General rules

- The server listens on `127.0.0.1` only. `quilate servir --host` with any other value is refused.
- The `LocalOnly` middleware refuses a `Host` header that is not `127.0.0.1` or `localhost` (with or without the port). For the WebSocket and for every method other than GET, HEAD and OPTIONS, it also refuses an `Origin` that is not the local server or the Vite dev server (`127.0.0.1:5173`, `localhost:5173`). A refused HTTP request gets `403 Acesso negado.` A refused WebSocket is closed with code 1008.
- There is no CORS and no OpenAPI page.
- There is no access code. Any program on the same Mac can call the API. See "Known gap" in [threat-model.md](threat-model.md).
- JSON keys are in English. Verdict values and user-facing text are in Portuguese: `Manter`, `Reduzir`, `Sair`.
- Money is in USD. Ratios such as `pnl_pct` and `share` are fractions: `0.05` means 5%.
- Times ending in `_utc` are ISO 8601 in UTC. Days are `YYYY-MM-DD` in the configured time zone.
- No GET route spends money or changes the portfolio.

## Routes

### `GET /api/overview` (notch)

Totals for the home page.

| Field | Type | Meaning |
|---|---|---|
| `total_usd` | number | Portfolio value now. |
| `total_brl` | number or null | Value in BRL. Null without the `usdbrl` market snapshot. |
| `invested_usd` | number | Average cost times quantity, for coins with a known cost. |
| `pnl_usd` | number | Unrealized result. |
| `pnl_pct` | number or null | `pnl_usd / invested_usd`. |
| `by_exchange` | list | `{exchange, usd, stale, share}` per exchange, largest first. `stale` is true when the last sync of that exchange failed. |
| `history` | list | `{ts, usd}` for the last 30 days. Approximation: today's quantities at each day's close. |
| `spent_month_usd` | number | AI spending this month, without one-time costs. |
| `budget_usd` | number | Monthly AI limit. |
| `budget_state` | string | `ok`, `alerta` (above `budget_alert_ratio`) or `bloqueado` (limit reached). |
| `last_cycle_utc` | string or null | When the last daily cycle wrote a verdict. |
| `playbook_approved` | boolean | Whether the analyst's playbook has an approved version. |
| `disclaimer` | string | The "not investment advice" line. |
| `analyst_name` | string | Display name from the settings. Empty means "o analista". |

The notch app reads `total_usd`, `total_brl`, `invested_usd`, `pnl_usd`, `pnl_pct`, `budget_state`, `last_cycle_utc` and `history`.

### `GET /api/verdicts` (notch)

Latest verdict of each coin for one day. Query: `day=YYYY-MM-DD` (optional, default: the latest day with verdicts).

Response: `{day, groups: {Sair: [card], Reduzir: [card], Manter: [card]}}`. Each group is sorted by value, largest first.

Card fields:

| Field | Type | Meaning |
|---|---|---|
| `symbol`, `name` | string | Ticker and name (name from CoinGecko, or the ticker). |
| `exchanges` | list of strings | Where you hold the coin. |
| `price_usd` | number | Live price, or the verdict price. |
| `change_24h` | number or null | Change against yesterday's close, as a fraction. |
| `value_usd` | number | Your position. |
| `pnl_usd` | number or null | Unrealized result. |
| `cost_unknown` | boolean | The average cost could not be computed. |
| `verdict` | string | Final verdict. |
| `rubric_verdict`, `ai_verdict` | string, string or null | The two inputs of the final verdict. |
| `confidence` | number or null | Claude's confidence, 0 to 1. |
| `alerts` | number | How many of the 7 signals are in alert. |
| `signals` | list | `{code, name, alert, value}`. `alert` is true, false or null (no data). |
| `reason` | string | First reason in favour (Manter) or against (Reduzir, Sair). |
| `no_analyst` | boolean | Signal S6 has no data: the analyst never mentioned the coin with a stance. |
| `flag` | string or null | `ai_paused` (spending limit) or `ai_failed`. |

The notch app reads `symbol`, `name`, `verdict`, `price_usd`, `change_24h`, `value_usd` and `pnl_usd`.

### `GET /api/coins/{symbol}`

One coin in detail. `symbol` must match `^[A-Z0-9]{1,15}$`. Returns 404 when the coin has no verdict.

All card fields, plus:

| Field | Type | Meaning |
|---|---|---|
| `avg_cost_usd` | number or null | Average cost. |
| `qty` | number | Total quantity. |
| `by_exchange` | list | `{exchange, wallet, qty}`. |
| `candles` | list | `{day, close}` for the last 90 days. |
| `pros`, `cons` | list of strings | Reasons for and against. |
| `main_risk` | string | Main risk. Marked as unreviewed while the playbook is not approved. |
| `quotes` | list | Up to 10 recent quotes from the analyst: `{id, text, date_utc, topic, kind, t_start}`. `kind` is `texto`, `foto`, `audio`, `transcricao` or `link`. `topic` comes from `[group_topics]`. |

### `GET /api/portfolio`

`{total_usd, coins: [...]}`. Each coin: `symbol`, `name`, `qty`, `price_usd`, `value_usd`, `share`, `avg_cost_usd`, `cost_unknown`, `pnl_usd`, `exchanges`, and `positions` as `{exchange, wallet, qty, stale, permissions_verified}`. `permissions_verified` is false for MEXC and Gate, whose key permissions were confirmed by the owner, not by the API.

### `GET /api/market`

One entry per source: `fng`, `cg_global`, `alt_season`, `btc_onchain`, `derivs`, `dxy`, `etf_flows`, `stablecoins`. Each entry is `{day, source, value}` from the latest snapshot, or null. `cg_global` also has `change_7d`: BTC dominance change in percentage points over 7 days, or null without 7 daily snapshots.

### `GET /api/track`

Hit rates. `by_verdict` and `by_signal` map a verdict or a signal code to horizons `"7"`, `"30"`, `"90"`, each `{n, hits, rate}`. `verdicts` lists the 100 most recent verdicts with results: `{id, day, symbol, verdict, outcomes: {"7": {r_hold, r_paper, r_btc, hit}}}`. See [signals.md](signals.md) for the hit rule.

### `GET /api/playbook`

The analyst's playbook. Shows the weekly draft when there is one, else the approved version.

| Field | Meaning |
|---|---|
| `version_id`, `markdown`, `approved` | The version shown. |
| `rules` | `{id, category, text, source_ids, approved}`. |
| `sources` | Map from source id (`m:<msg_id>` or `c:<chunk_id>`) to `{date_utc, topic, kind, text, url, t_start}`. |
| `timeline` | Last 10 analyst messages in the trigger topic. Empty when `trigger_topic` is 0. |
| `lives` | Last 10 YouTube jobs: `{url, status, date_utc}`. |
| `lives_count` | Count of YouTube jobs per status. |
| `trigger_topic_name` | Name of the trigger topic from `[group_topics]`, or null. |

### `POST /api/playbook/rules/{rule_id}/approve`

Approves one rule. Returns `{ok, playbook_approved}`. 404 for an unknown rule. When every rule of a version is approved, the version becomes approved.

### `GET /api/costs` (notch)

| Field | Meaning |
|---|---|
| `spent_month_usd`, `budget_usd`, `budget_state` | Same as in the overview. |
| `one_time_usd` | Total one-time cost (the initial playbook). Not part of the monthly sum. |
| `by_purpose`, `by_model` | This month's recurring cost, `{purpose, usd}` and `{model, usd}`. |

The notch app reads `spent_month_usd`, `budget_usd` and `budget_state`.

### `POST /api/cost-overrides`

Body: `{symbol, avg_cost_usd, qty?, note?}`. `avg_cost_usd` and `qty` must be above 0. `note` has up to 500 characters. Sets a manual average cost for the coin. Returns `{ok, ...body}`.

### `POST /api/csv/{exchange}`

`exchange` is `binance`, `mexc`, `bybit` or `gate`. The body is the raw CSV file exported by the exchange (no multipart), up to 5 MB. Returns `{imported, read}`. 413 above 5 MB. 422 when the file does not match that exchange's format.

### `WS /ws`

Server-to-client events. Messages from the client are read and ignored.

| Event | Fields | When |
|---|---|---|
| `tick` | `symbol`, `price_usd`, `ts` (ms) | Live price. At most 2 per second per coin. |
| `verdict` | `symbol` | A coin was recomputed outside the daily cycle. |
| `cycle` | `day` | The daily cycle finished. |

## Setup routes

The setup page uses these routes. They work in setup mode and in full mode. They never return a secret value.

| Route | Body | Response |
|---|---|---|
| `GET /api/setup` | | `mode` (`setup` or `full`), `secrets` (name to boolean: exists or not), `config`, `data` (row counts and whether a playbook exists), `checklist` (`{id, label, done, how}`), `restart_required`, `missing_for_serve`, `required_secrets`. |
| `POST /api/setup/secrets/{name}` | `{value}` (1 to 4,096 characters) | `{ok, name}`. Writes to the Keychain. 404 for a name outside `SECRET_NAMES`. |
| `DELETE /api/setup/secrets/{name}` | | `{ok, name}`. |
| `PUT /api/setup/config` | Any of `owner_name`, `analyst_username`, `analyst_name`, `confirmed_read_only`, `budget_usd`, `budget_alert_ratio`, `dust_usd`, `cutoff_hour`, `intraday_move`, `sync_minutes` | `{ok, config, restart_required}`. Writes `config.local.toml`. 422 when nothing is valid or when `confirmed_read_only` lists an exchange other than MEXC or Gate. |
| `POST /api/setup/check-keys` | | `{exchanges: [{exchange, status, detail}], safe}`. `status` is `ok`, `missing`, `unconfirmed`, `unsafe` or `error`. |
| `POST /api/setup/telegram/send-code` | `{phone}` | `{ok}`. 409 without `telegram_api_id` and `telegram_api_hash`. 502 when Telegram refuses. |
| `POST /api/setup/telegram/sign-in` | `{code, password?}` | `{ok, username}`, or `{ok: false, needs_password: true}` when the account has two-step verification. Saves the session in the Keychain. |
| `POST /api/setup/restart` | | `{ok}`. Stops the server. `servir` then replaces its own process with the same command. |

Changes to `sync_minutes`, `confirmed_read_only` and `analyst_username` need a restart.

## Changing a route the notch app reads

`/api/overview`, `/api/verdicts` and `/api/costs` are a contract with `notch/Sources/QuilateNotch/Model.swift`. If you rename or remove a field the app reads, update `Model.swift` and the files in `notch/Tests/Fixtures/` in the same pull request.

Any other route not listed here returns the dashboard's `index.html`, or 404 under `/api/`.
