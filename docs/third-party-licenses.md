# Third-party licenses

Direct dependencies only. Transitive dependencies are not listed here; they are pinned in `backend/uv.lock` and `frontend/package-lock.json`.
Quilate is licensed under AGPL-3.0-or-later. All licenses below are compatible with it.
The Swift app in `notch/` has no third-party dependencies.

Sources: `pip-licenses` (backend, run inside the project environment) and `license-checker` (frontend), read on 2026-11-10 against the locked versions. Neither tool is a dependency of the project.
Where `pip-licenses` printed a trove classifier ("BSD License"), the SPDX identifier was taken from the package metadata.

## Backend (Python)

| Package | Version | License | Use | Compatible with AGPL-3.0 |
|---|---|---|---|---|
| APScheduler | 3.11.3 | MIT | runtime | Yes |
| Telethon | 1.45.0 | MIT | runtime | Yes |
| anthropic | 2.5.0 | Apache-2.0 (MIT files also shipped) | runtime | Yes |
| ccxt | 4.5.92 | MIT | runtime | Yes |
| fastapi | 0.162.0 | MIT | runtime | Yes |
| httpx | 0.28.1 | BSD-3-Clause | runtime | Yes |
| keyring | 25.7.0 | MIT | runtime | Yes |
| mlx-whisper | 0.4.3 | MIT | runtime | Yes |
| pydantic | 2.14.2 | MIT | runtime | Yes |
| sentence-transformers | 6.2.0 | Apache-2.0 | runtime | Yes |
| sqlite-vec | 0.1.9 | MIT or Apache-2.0 (dual) | runtime | Yes |
| trafilatura | 2.1.0 | Apache-2.0 | runtime | Yes |
| uvicorn | 0.54.0 | BSD-3-Clause | runtime | Yes |
| yt-dlp | 2026.10.26 | Unlicense | runtime | Yes |
| pytest | 9.2.0 | MIT | dev | Yes |
| pytest-asyncio | 1.4.1.post1 | Apache-2.0 | dev | Yes |
| respx | 0.23.1 | BSD-3-Clause | dev | Yes |
| ruff | 0.17.3 | MIT | dev | Yes |

## Frontend (npm)

| Package | Version | License | Use | Compatible with AGPL-3.0 |
|---|---|---|---|---|
| @fontsource-variable/geist | 5.3.0 | OFL-1.1 | runtime | Yes |
| @fontsource-variable/geist-mono | 5.3.0 | OFL-1.1 | runtime | Yes |
| lightweight-charts | 5.2.1 | Apache-2.0 | runtime | Yes |
| motion | 14.9.1 | MIT | runtime | Yes |
| react | 19.3.1 | MIT | runtime | Yes |
| react-dom | 19.3.1 | MIT | runtime | Yes |
| react-router | 8.5.1 | MIT | runtime | Yes |
| @tailwindcss/vite | 4.3.4 | MIT | dev | Yes |
| @testing-library/dom | 10.4.2 | MIT | dev | Yes |
| @testing-library/jest-dom | 7.0.1 | MIT | dev | Yes |
| @testing-library/react | 16.3.3 | MIT | dev | Yes |
| @types/node | 26.6.6 | MIT | dev | Yes |
| @types/react | 19.3.0 | MIT | dev | Yes |
| @types/react-dom | 19.3.0 | MIT | dev | Yes |
| @vitejs/plugin-react | 6.2.1 | MIT | dev | Yes |
| jsdom | 30.1.3 | MIT | dev | Yes |
| tailwindcss | 4.3.4 | MIT | dev | Yes |
| typescript | 7.0.2 | Apache-2.0 | dev | Yes |
| vite | 8.3.5 | MIT | dev | Yes |
| vitest | 5.1.0 | MIT | dev | Yes |

`@fontsource-variable/geist` and `@fontsource-variable/geist-mono` package the Geist and Geist Mono fonts (SIL Open Font License 1.1). They are bundled into the built dashboard, which is git-ignored, not committed to the repository.

`lightweight-charts` asks every product that uses it to name TradingView as its creator and to link to <https://www.tradingview.com/> where users can see it. The dashboard does this with the library's `layout.attributionLogo` option, which is on by default and is not turned off in `frontend/src/components/PriceChart.tsx`. The logo shows in the bottom-left corner of each price chart. The credit line is in the root `NOTICE`.

## Downloaded at run time (not packages, not redistributed by this repository)

| Asset | Where it is used | License or terms | Compatible with AGPL-3.0 |
|---|---|---|---|
| `google/embeddinggemma-300m` | `backend/quilate/knowledge/embed.py` | Gemma Terms of Use (not an OSI license; gated, the user must accept it on Hugging Face and supply a read token). | Not applicable: the model is not distributed with Quilate, and each user accepts the terms for their own download. |
| `mlx-community/whisper-large-v3-turbo` | `backend/quilate/media/transcribe.py`, through `mlx-whisper` | The `mlx-community` model card declares no license. The upstream `openai/whisper-large-v3-turbo` is MIT. | Not applicable: not distributed with Quilate. Upstream MIT is compatible. |

Quilate does not ship these files. Each user downloads them to their own machine on first use.

## Result

No direct dependency has a license outside the compatible list, and none lacks a license.
The only `UNLICENSED` line in the raw `license-checker` output is the `quilate-dashboard` package itself, before the license field was added.
Apache-2.0 dependencies that ship their own `NOTICE` file are credited in the root `NOTICE`: `sentence-transformers` and `typescript` (development only). `lightweight-charts` is also credited there, for the TradingView attribution.
