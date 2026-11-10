# Install

This page installs the full system with your real accounts. To look at the dashboard first, with fake data and no accounts, follow "Try it in two minutes" in the [README](../README.md).

Quilate only reads. It never buys, sells, withdraws or transfers. It is not investment advice.

## Requirements

- A Mac with Apple Silicon. Transcription uses `mlx-whisper`, which runs only there.
- [uv](https://docs.astral.sh/uv/) and the Homebrew Python 3.12: `brew install python@3.12`. The Python that uv downloads by itself cannot load the `sqlite-vec` extension.
- Node 22.12 or newer, for the dashboard.
- Xcode or the Command Line Tools with Swift 6, only for the notch app.

Accounts and keys:

- An Anthropic API key.
- Telegram: `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org), the ID of the group you want to read, and a bot created with @BotFather plus the ID of your chat with it.
- A **read-only key, without withdrawal**, on each exchange you use: Binance, MEXC, Bybit, Gate.
- Free keys for CoinGecko (Demo), Coinalyze and FRED. CoinGlass is optional.
- A Hugging Face read token, after you accept the license of [`google/embeddinggemma-300m`](https://huggingface.co/google/embeddinggemma-300m).

## Steps

1. Clone and build. The setup page shows commands that assume the clone is at `~/quilate`.

   ```sh
   git clone https://github.com/trivixlabs/quilate ~/quilate
   cd ~/quilate/frontend && npm ci && npm run build
   cd ~/quilate/backend && uv sync --python "$(brew --prefix python@3.12)/bin/python3.12"
   ```

   `npm run build` writes the dashboard to `backend/quilate/api/static`. Git ignores that folder, so a fresh clone needs this step before `servir`.

2. Write your community settings. Copy the model and edit it. [configuration.md](configuration.md) explains each key.

   ```sh
   cp quilate/config.local.example.toml quilate/config.local.toml
   ```

   You can also set `analyst_username` and `analyst_name` on the setup page in step 4.

3. Start the server.

   ```sh
   uv run quilate servir
   ```

   Without the required secrets, the server starts in **setup mode**: only the API and the setup page, with no exchange, scheduler or Telegram. It opens `http://127.0.0.1:8000/configuracao` in your browser.

4. Follow the checklist on the setup page. It writes each secret straight to the Keychain and never shows it back. It guides you through the read-only key on each exchange, the Telegram app and login, the alert bot, the Claude key, the market data keys and the Hugging Face token. For MEXC and Gate, check on the exchange site that the key is read-only, then tick the confirmation. The "Checar chaves" button asks each exchange what the key can do.

5. Run two steps in the terminal. One is slow, the other costs money. The setup page shows both commands with a copy button.

   ```sh
   uv run quilate importar --meses 12
   uv run quilate manual-inicial
   ```

   `importar` reads 12 months of the group. Older history comes in later, one batch per hour, while `servir` runs. `manual-inicial` shows the estimated cost of the initial playbook and runs only if you type `s`. If it stops in the middle, run it again: the parts already extracted are not paid twice.

6. With the required secrets saved, click "Reiniciar o servidor" on the setup page. `servir` now starts in full mode: it checks the keys, connects the exchanges, the scheduler and Telegram. It refuses to start with a key that allows trading or withdrawal.

7. Import the CSV history of each exchange on the "Carteira" page. This is required for Bybit: its API returns only the last 7 days of trades, so the average cost is wrong without the CSV.

The required secrets for full mode are `anthropic_api_key`, `telegram_api_id`, `telegram_api_hash`, `telegram_group_id`, `telegram_bot_token` and `telegram_chat_id`, plus `analyst_username` in the settings.

## Terminal only

You can skip the setup page. Save each secret with `uv run quilate segredo <name>`. The value is typed without echo. The names are in `backend/quilate/secrets.py`. Log in to Telegram with `uv run quilate telegram-login`. The session goes to the Keychain, and no `.session` file is written.

Never run `huggingface-cli login`. It writes the token to a file. Use `uv run quilate segredo hf_token`.

## Commands

| Command | What it does |
|---|---|
| `quilate segredo <name>` | Saves one secret in the Keychain. |
| `quilate telegram-login` | Telegram login. Asks for phone, code and two-step password. |
| `quilate checar-chaves` | Checks that the exchange keys are read-only. |
| `quilate importar --meses N` | Imports N months of the group. |
| `quilate manual-inicial` | Estimates the cost and builds the initial playbook, after confirmation. |
| `quilate ciclo` | Runs the daily cycle now. |
| `quilate servir [--porta N]` | Starts the dashboard, the API and the scheduler on `127.0.0.1`. |

Run them inside `backend/` with `uv run`.

## Start at login

```sh
cd ~/quilate && sh ops/instalar-launchd.sh
```

The script writes the LaunchAgent `io.github.trivixlabs.quilate` with the paths of this Mac and loads it. The log goes to `~/quilate-dados/logs/quilate.log`. To remove it: `sh ops/instalar-launchd.sh remover`. The agent does not restart the server if it crashes. It comes back at the next login.

## Notch app

```sh
cd ~/quilate/notch && ./build.sh && open Quilate.app
```

The app reads the backend on `127.0.0.1:8000`. See [notch/README.md](../notch/README.md).

## After the first sync

Check these with your real data. Details in [verification.md](verification.md).

- Compare the average cost of 3 coins with the exchange site.
- Check that each CSV reader matches the header of your real export file.
- MEXC and Bybit fees in another coin are assumed to be in the quote coin.
- Binance fees paid in BNB in the CSV are read as zero for now.
