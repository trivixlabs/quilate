# Threat model

Quilate is a local tool for one person on one Mac. It reads a crypto portfolio on four exchanges, reads a Telegram group, and gives a daily verdict per coin. This page lists what it protects, how, and what it does not protect. Each point names the code that does the work.

## What Quilate never does

- It never buys, sells, withdraws or transfers. No code path places an order or moves funds.
- It never writes to the Telegram group. The collector only reads (`backend/quilate/telegram/collector.py`). The bot only sends summaries and alerts to the chat you configure (`telegram/bot.py`).
- It never opens the server to the network. The server binds to `127.0.0.1` (`cli.py`, `HOST`).

## Exchange keys

Keys must be read-only. `ExchangeClient.check_read_only` (`exchanges/client.py`) fails closed:

- Binance and Bybit report key permissions through their APIs. A key that allows trading, withdrawal or transfer, or a missing permission field, raises `UnsafeKeyError`.
- MEXC and Gate do not report permissions. They are refused until the owner lists the exchange in `confirmed_read_only` in `config.local.toml`, after checking on the exchange site.
- On `UnsafeKeyError`, sync stops (`cycle.py`, `cli.py`).

## Where secrets live

All secrets are in the macOS Keychain, service `quilate` (`secrets.py`). They enter through the `quilate segredo` command or through the setup page, which posts to `127.0.0.1` and writes straight to the Keychain (`api/setup.py`). The API never returns a secret, only whether it exists. The Telegram session is a `StringSession`, so nothing is written to disk (`telegram/collector.py`, `cli.py`).

The data folder `~/quilate-dados` is created with mode `0700` (`cli.py`), so other macOS accounts cannot read the portfolio or the group messages.

## Host and Origin checks

The `LocalOnly` middleware (`api/app.py`) rejects any HTTP or WebSocket request whose `Host` is not `127.0.0.1` or `localhost` (with the server port). This blocks DNS rebinding. For WebSocket and for requests that change data (anything other than GET, HEAD and OPTIONS), it also rejects an `Origin` that is not the local server or the Vite dev server. This blocks cross-site requests from a browser. A request with no `Origin` header passes, because browsers always send one and `curl` does not. So `curl` and any other local program pass these checks. See "Known gap".

## Text from third parties

Messages from the group, the analyst's text and audio transcripts are data, not instructions. Before they go into a prompt, they pass through `html.escape`, so they cannot close a prompt block or open a fake one (`ai/verdict.py`, `ai/playbook.py`, `knowledge/mentions.py`). The model output is parsed against a schema and validated (`ai/claude.py`).

## Link fetching

When a message links to a page, `media/links.py` fetches it with these limits:

- Only `http` and `https`, only to public addresses. `localhost`, private, loopback and link-local addresses are refused (`_public`, which uses `ipaddress.is_global`). A host name is resolved, and every address must be public.
- Redirects are followed by hand, up to 5 hops, and each hop goes through the same check.
- A response larger than 5 MB is dropped, but the size is checked after the download, not during it. The 20 s value is the httpx timeout for each phase of a request, not a total deadline.
- Limitation: the name is resolved once by the check and again by the HTTP client. A DNS server that changes its answer between the two lookups could pass the check. The code marks this with a comment.

## Spending limit

Every Claude API call goes through `ai/claude.py`, which records the cost of each call. Before a call, `Claude.parse` refuses it when the recurring spending of the month has reached `budget_usd` (`ai/claude.py`, `budget.py`: `budget_state` returns `bloqueado`).

- Only the weekly playbook update also checks, before the call, that the estimated cost fits in what is left of the limit (`Claude.fits`, used in `ai/playbook.py`). The other calls (verdicts, mentions, initial playbook) have only the check above. A call that starts below the limit can end above it, by the cost of that call.
- The one-time cost of the initial playbook (`one_time=True`) is not part of the monthly sum (`month_spent` in `budget.py`). It is recorded and shown separately, and it does not count toward the limit.

## Known gap

The local API has no password. The Host and Origin checks stop websites in your browser. They do not stop another program, or another user account on the same Mac, from calling the API. A local caller can do everything the dashboard and the setup page do:

- read the portfolio, the verdicts and everything else the `GET` routes return;
- write or delete any secret in the Keychain (`POST` and `DELETE /api/setup/secrets/<name>`), including the bot token and chat ID that decide where alerts go, and replace the Telegram session through `/api/setup/telegram/send-code` and `/api/setup/telegram/sign-in`;
- change the local configuration (`PUT /api/setup/config`): raise `budget_usd`, mark MEXC and Gate as confirmed read-only, or change `analyst_username` and `analyst_name`;
- approve a playbook rule, record an average cost and import trades from a CSV (`api/app.py`);
- restart the server (`POST /api/setup/restart`);
- make the server check the stored exchange keys against the exchanges (`POST /api/setup/check-keys`). The answer carries only the status of each key.

No route returns the value of a secret. A local caller can replace a secret, but cannot read it through the API.

This does not block the public release. The first public issue proposes an access code generated when the server starts.
