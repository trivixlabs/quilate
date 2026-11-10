# Security

Quilate runs only on your own Mac. It has no hosted service and no account system.
This file says what it stores, where, and how to report a vulnerability. The full model is in [docs/threat-model.md](docs/threat-model.md).

## What Quilate stores, and where

- **Secrets** (exchange read-only keys, Anthropic key, Telegram credentials and session, bot token, chat ID, data API keys, Hugging Face token): in the macOS Keychain, service `quilate`. Never in `.env`, `.session` files, logs, tests, API responses or commits. The API only says whether a secret exists.
- **Data** (portfolio, trades, messages from the Telegram group, transcripts, verdicts, API costs): in `~/quilate-dados`, a folder created with mode `0700`. This folder is never committed.
- **Local configuration** that identifies your group and people: `backend/quilate/config.local.toml`. It is ignored by Git.

## What Quilate never does

It only recommends. It never buys, sells, withdraws or transfers. It refuses exchange keys that allow trading or withdrawal. It never writes to the Telegram group. It listens on `127.0.0.1` only.

## Known gap

The local API has no password. Host and Origin checks block websites in your browser, but not another program or another user account on the same Mac. Such a program can read the portfolio, write or delete any secret, change the local configuration (including the monthly limit and the MEXC and Gate confirmation), approve playbook rules, record average costs, import trades and restart the server. The API never returns the value of a secret. See "Known gap" in the threat model.

## Reporting a vulnerability

Use GitHub private vulnerability reporting: https://github.com/trivixlabs/quilate/security/advisories/new

Do not open a public issue for a security problem. Do not include real keys, tokens or personal data in the report. If you found a leaked secret, say where, and revoke it first.

We will confirm receipt, tell you whether we accept the report as a vulnerability, and credit you in the fix if you want. This is a volunteer project, so response times are best effort.

## Supported versions

Only the latest commit on `main`.
