# Web Companion

## Run

```powershell
uv sync
cd app/web
npm ci
npm run build
cd ../..
uv run xinbot start web
```

Open http://127.0.0.1:3796. The server binds to loopback only. For development,
run `xinbot start web --dev` and `npm run dev` in `app/web`; Vite proxies to 3796.

## Characters

- Existing XinBot personas remain readable without migration.
- Import Character Card V2 JSON or PNG with base64 `chara` metadata. Legacy JSON
  cards are normalized to V2. Maximum input size is 20 MB.
- Description, personality, scenario, dialogue examples and system instructions
  are incorporated into the persona prompt. Post-history instructions are appended
  after chat history. `{{char}}` and `{{user}}` are substituted.
- First message initializes an empty character conversation. Activating a character
  selects `web-{character-id}` memory; existing default memory is not deleted.
- Alternate greetings, creator notes, tags, worldbooks and unknown extensions are
  preserved on JSON export. Worldbook activation, Tavern scripts, advanced macros,
  V3 cards and PNG export are not implemented.
- Appearance and character identity are independent; each character can bind a pet.

## Models And Credentials

The connection page supports OpenAI-compatible providers and explicit model IDs.
API keys are saved in the local `.env`, excluded from Git, and never returned by
the settings endpoints. An empty key preserves the existing credential. This is
local plaintext configuration, not an encrypted credential vault.

The web agent refuses dangerous tools by default; it cannot use terminal approval
prompts. The existing Agent yields complete response chunks, so the WebSocket
transport is not token-by-token provider streaming.

## Pet Assets

- Live2D Cubism `.model3.json` packages render through PixiJS and
  `pixi-live2d-display`, with local Cubism Core, motions and pointer interaction.
- The included test location `pet/codexpet/kaguya` uses the Codex 8-column,
  9-row sprite layout. This adapter is not a claim to support every ChatGPT/Codex
  pet asset format.
- Import ZIP packages containing the model and its local referenced assets, or
  `pet.json` plus `spritesheetPath`. Archives are path-checked and size-limited.
- `scripts/download_live2d.py` downloads the official Haru sample and Cubism Core
  for local evaluation. Downloaded assets are ignored by Git. Source:
  https://github.com/Live2D/CubismWebSamples/tree/develop/Samples/Resources/Haru
- Haru and Cubism Core are third-party licensed assets. Review the downloaded
  `app/web/static/models/haru/LICENSE.md`, the Live2D Free Material License and
  Cubism SDK Release License before redistribution or commercial release:
  https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html
  https://www.live2d.com/en/download/cubism-sdk/release-license/

The pet currently lives inside the browser. Transparent always-on-top OS windows,
tray integration and desktop click-through remain separate desktop-shell work.

## Verification

```powershell
uv run pytest tests/test_web_cards.py -q
cd app/web
npm run build
npx playwright test --workers=1
```

Browser tests use a running local server, Microsoft Edge by default, and mocked
chat/history responses to avoid sending paid LLM requests or editing real chats.
They inspect Live2D and sprite canvas pixels, animation, mobile overflow and forms.
Set `PLAYWRIGHT_CHANNEL=chromium` to use an installed Playwright Chromium instead.
