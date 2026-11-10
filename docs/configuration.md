# Configuration

Quilate reads two files in `backend/quilate/`:

- `config.toml` is in Git. It has the defaults that are the same for everyone.
- `config.local.toml` is not in Git. It has what identifies your community and the people in it, and any default you want to change. Copy `config.local.example.toml` to start.

`load_settings()` in `config.py` reads `config.toml` and then applies `config.local.toml` on top. Rules:

- Any key of `config.toml` can be overridden in the local file.
- A table in the local file replaces the whole table. If you override `[thresholds]`, write all of its keys.
- A key that `config.toml` does not have makes Quilate refuse the local file. The error names the key.
- The setup page (`/configuracao`) can write some keys to `config.local.toml` for you. It keeps your values and tables, but it drops the comments. The commented model stays in `config.local.example.toml`.

Secrets never go in these files. They go in the macOS Keychain (see [install.md](install.md)).

## The community

These four settings tell Quilate who the analyst is and how the group is organized. The values below are the made-up ones from `config.local.example.toml`.

```toml
analyst_username = "usuario_do_analista"
analyst_name = "Ana"
trigger_topic = 101

[group_topics]
101 = "MARKET UPDATES"
102 = "GENERAL"
```

| Key | Default | Meaning |
|---|---|---|
| `analyst_username` | `""` | Telegram username of the person who posts the analyses, without `@`. Only this person's messages count as analysis. Audio and links are processed only for this person. The other members are context: mentions and sentiment for signal S7. Required: without it, `servir` starts in setup mode and `importar` refuses to run. |
| `analyst_name` | `""` | Display name of the analyst on the dashboard, in bot messages and in the AI prompts. Empty means the texts say "o analista". |
| `trigger_topic` | `0` | Number of the group topic where the analyst posts the daily analysis. A message from the analyst in this topic starts the daily cycle. With `0`, the cycle runs only at `cutoff_hour`. |
| `[group_topics]` | empty | Names of the group topics, by topic number. The dashboard shows the name next to each quote. The playbook page shows the name of the trigger topic. Only the local file has this table. The setup page does not edit it. |

The setup page edits `analyst_username` and `analyst_name`. `trigger_topic` and `[group_topics]` are edited only in the file.

## General settings

| Key | Default | Meaning | Setup page |
|---|---|---|---|
| `owner_name` | `""` | Your name. Only shown on the dashboard. | yes |
| `data_dir` | `"~/quilate-dados"` | Database, media and logs. | no |
| `tz` | `"America/Sao_Paulo"` | Time zone for days, the 3:00 market snapshot and the cut-off hour. | no |
| `budget_usd` | `50` | Monthly AI limit in USD. | yes |
| `budget_alert_ratio` | `0.8` | Above this share of the limit, the state is `alerta`. | yes |
| `dust_usd` | `10` | Coins worth less than this get no verdict. | yes |
| `cutoff_hour` | `12` | Hour when the daily cycle runs if the analyst has not posted in the trigger topic. | yes |
| `intraday_move` | `0.10` | Price move from yesterday's close that recomputes a coin (10%). | yes |
| `sync_minutes` | `5` | Exchange sync and price-move check interval, 1 to 60. Below 5, exchanges may rate-limit you. Needs a restart. | yes |
| `symbol_aliases` | `{ XBT = "BTC", MATIC = "POL" }` | Tickers that mean the same coin. | no |
| `confirmed_read_only` | `[]` | MEXC and Gate do not report key permissions. Quilate refuses their keys until you check on the exchange site that the key cannot trade, withdraw or transfer, and list the exchange here: `["mexc", "gate"]`. Binance and Bybit are checked through their APIs. Needs a restart. | yes |
| `ambiguous_tickers` | `["LINK", "OP", ...]` | Tickers that are also common words. They count as a mention only as `$ticker` or in capital letters. | no |

## Thresholds

`[thresholds]` holds the limits of the 7 signals. [signals.md](signals.md) explains each one.

## AI prices

`[prices.<model>]` holds the price per million tokens of each Claude model: `input`, `output`, `cache_read`, `cache_write_1h`. A model can also have `long_prompt_tokens` and `long_prompt_mult`: a request with a prompt above that size (input plus cache) pays the multiplier on everything. The prices were checked on the official Anthropic pricing page on 2026-11-09. Check them again before you rely on the cost numbers.

## Spending limit

Every call to the Claude API goes through `backend/quilate/ai/claude.py`, which records its cost.

- When the recurring spending of the month reaches `budget_usd`, every AI call is refused. The verdicts then come from the rubric only.
- Only the weekly playbook update checks first that its estimated cost fits in what is left of the limit. If it does not fit, it waits for the next week.
- A call that starts below the limit can end above it, by the cost of that call.
- The one-time cost of the initial playbook is not part of the monthly sum. It is shown separately.
