# AGENTS.md for the frontend

React 19, Vite, strict TypeScript, Tailwind 4, `motion`, `lightweight-charts`, `react-router`, Vitest with jsdom. General rules are in the root `AGENTS.md`.

## Structure

- `src/lib/api.ts`: every HTTP call. One function per route. No `fetch` outside this file.
- `src/lib/types.ts`: mirror of the responses of `backend/quilate/api/app.py` (documented in `docs/api.md`). If the API changes, change it here and in the fixtures.
- `src/lib/live.ts`: WebSocket `/ws`, `LiveProvider`, `useLive`, `useLiveQuery`. Reconnects with backoff up to 30 s.
- `src/lib/format.ts`: money, percentage and date in pt-BR.
- `src/pages/`: `Vereditos` (home, "Visão geral" tab: portfolio value, exchanges, market gauge and the three columns), `Moeda`, `Carteira`, `Analista`, `Mercado`, `Historico`, `Configuracao` (6-step wizard: Você, Corretoras, Telegram, IA e mercado, Primeira carga, Preferências. Each step closes checklist ids from `api/setup.py`, mapped in `STAGES`).
- `src/components/`: `AppShell` (sidebar in three groups: Acompanhar, Entender, Sistema), `VerdictCard`, `SignalBar`, `SignalList`, `PriceChart`, `PortfolioHero`, `AnalystQuotes`, `CsvUpload`, `CostOverrideForm`, `LoadState`.
- `src/styles/theme.css`: color tokens and fonts (Geist). Tailwind classes in JSX, no CSS per component.
- `src/test/fixtures.ts`: fake data and `demoApi`. Same shape as the real API.

## Commands

```sh
npm ci
npm test            # vitest run
npm run build       # tsc --noEmit && vite build, output in ../backend/quilate/api/static
npm run dev         # 127.0.0.1:5173, proxies /api and /ws to 127.0.0.1:8000
```

`?demo=1` on the dev server swaps `fetch` for `demoApi`. The production build removes this branch.

## Conventions

- Components in PascalCase, one per file, with the test next to it (`X.test.tsx`).
- Tests render with `render(ui, { api, route })` from `src/test/render.tsx`. `api` is a fake `fetch` that returns the fixtures. The WebSocket never connects in tests.
- `lightweight-charts` is mocked in `src/test/setup.ts` because jsdom has no canvas. A chart test checks calls, not pixels.
- `lightweight-charts` (Apache-2.0) asks for attribution to TradingView. Keep `layout.attributionLogo` at its default (on) in `PriceChart.tsx`. See `NOTICE`.
- State comes from the server. No global store besides `LiveProvider`.
- Text on screen in Portuguese. USD values through `format.ts`. A verdict always uses the three fixed colors of `theme.css`.
- Animation only with `motion` and only where it shows a change: a price that flashes, a card that moves to another group. Nothing decorative in a loop.
- No secret, token or call to an external URL in the bundle. The frontend only talks to `127.0.0.1:8000`. The only exception is `LINKS` and `EXCHANGES[].url` in `Configuracao.tsx`: `<a target="_blank" rel="noopener noreferrer">` links to the key page of each service, opened by the user. Nothing is fetched from them.
- A secret typed on the setup page exists only in the `<input type="password">` until the POST, and the field comes back empty. It never goes to global state, the URL, a log or text on screen. The test checks that the value is not in the DOM after saving.
