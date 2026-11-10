# AGENTS.md for the notch app

macOS app in Swift that shows, in the notch, the portfolio read from the local Quilate backend. Read-only: it never trades, never talks to an exchange or to Telegram, keeps no secret and writes nothing to disk. The `README.md` explains how to use it. General rules are in the root `AGENTS.md`.

## Commands

```sh
swift build        # debug
swift test         # 10 model tests, no network
./build.sh         # release build + Quilate.app, ad hoc signed
open Quilate.app
./demo.sh          # serves Tests/Fixtures on 127.0.0.1:8000, no backend needed
```

## Conventions

- SwiftUI and AppKit only. No third-party dependency. `Package.swift` with `platforms: [.macOS(.v15)]`. The SwiftPM target is `QuilateNotch`. The app bundle is `Quilate.app`.
- Identifiers in English. User-facing text and comments in Portuguese. Docs in English. Existing comments stay in Portuguese, and a new comment can be in English or Portuguese. Commits in Portuguese or English.
- Commits follow Conventional Commits (`feat:`, `fix:`, `docs:`), subject up to 72 characters.
- New tests go in `Tests/QuilateNotchTests/ModelTests.swift`, with Swift Testing (`@Test`, `#expect`). JSON examples in `Tests/Fixtures/`, in the format of `backend/quilate/api/app.py`.
- API format: `Model.swift` decodes only the fields it uses, with explicit `CodingKeys`. A new field goes there and in the fixture. The contract is in `docs/api.md`.
- A verdict always has a color and an icon (`Verdict.color`, `Verdict.symbol`). Color alone is not enough. The 24 h change uses the color of the direction (`gainColor`), not the color of the verdict.
- `coinHue` follows the same math as `hue()` in `frontend/src/components/VerdictCard.tsx`. If it changes there, change it here and in the test `corDaMoedaIgualAoDashboard`.

## Pitfalls

- A stored global variable in an executable module is nil inside `swift test` (SwiftPM). Use a computed or `static` property. That is why `ptBR` is a `var`.
- `convertFromSnakeCase` turns `change_24h` into `change24H`, not `change24h`. That is why the `CodingKeys` are explicit.
- The window always has the size of the drawing (`onGeometryChange` in `NotchPanel.resize`). Without it, the window blocks clicks on the menu bar.
- `NSPanel` with `canBecomeKey = false` and `.nonactivatingPanel`: the app never steals focus.
- Backend down sets `Carteira.offline` and keeps the last data on screen. Never throw an error to the view.
- Coin cards come from `/api/verdicts`, not from `/api/overview`. The overview only has the totals.
- `demo.sh` refuses to start when port 8000 is in use. Stop the backend first.
