# Function map: reference ComfyUI-Photoshop → ComfyUI-PhotoCraft

Every reference feature has a corresponding implementation (or a stated
equivalent) in this repo. Nothing is left as a bare TODO. “Equivalent”
means the same user-visible outcome via PhotoCraft's real extension
points (control channel / CLI / files), not a literal port of the
Photoshop-only mechanism.

| # | Reference ComfyUI-Photoshop feature | ComfyUI-PhotoCraft implementation | Location |
|---|---|---|---|
| 1 | Photoshop UXP panel inside Photoshop | **Equivalent:** standalone local web side panel, opened in a browser next to PhotoCraft (PhotoCraft has no UXP panel) | `photocraft_panel/index.html`, `app.js`, `styles.css` |
| 2 | Ai Panel / Settings / ComfyUI Web tabs | Same three tabs in the side panel | `photocraft_panel/index.html` |
| 3 | Positive / negative prompts, seed, slider | Same fields in panel + `config.json` + node inputs | `photocraft_panel/app.js`, `py/nodes.py` (`PhotoCraftToComfyUI`) |
| 4 | Photoshop → ComfyUI input node (canvas / mask / config) | `PhotoCraftToComfyUI`: reads `data/pc_inputs/PC_canvas.png`, `PC_mask.png`, `config.json`; outputs `(IMAGE, MASK, FLOAT, INT, STRING, STRING, INT, INT, STRING, STRING)` | `py/nodes.py` |
| 5 | `IS_CHANGED` / change detection | MD5 of the three input files | `py/nodes.py` (`_inputs_signature`, `IS_CHANGED`) |
| 6 | ComfyUI → Photoshop output node (SaveImage-style) | `ComfyUIToPhotoCraft`: saves PNG, `GET /pc/renderdone?filename=…`, `last_render.json` sidecar | `py/nodes.py` |
| 7 | ClipPass / ModelPass pass-through | `ClipPass` (CLIP), `ModelPass` (MODEL), unchanged pass-through | `py/nodes.py` |
| 8 | Photoshop remote connection node (ExtendScript / photoshop-connection) | **Equivalent:** `PhotoCraftControl` via PhotoCraft JSON control channel (`engine.execute`), live mode. No ExtendScript, no `photoshop-connection` | `py/nodes.py`, `py/photocraft_adapter.py` |
| 9 | WebSocket backend `/ps/ws` (platform ps/cm) | `/pc/ws` (platform pc/cm), token-authenticated, loopback-only | `py/backend.py` |
| 10 | HTTP `/ps/workflows`, `/ps/inputs`, `/ps/renderdone` | `/pc/workflows/{name}`, `/pc/inputs/{filename}`, `/pc/renderdone`, plus `/pc/status`, `/pc/command` | `py/backend.py` |
| 11 | Message types canvas / mask / config / workspace / queue / progress / render / alert | Same types, renamed to `canvasBase64 / maskBase64 / configdata / workspace / queue / progress / render / photocraftConnected / alert` | `py/backend.py`, `js/connection.js`, `js/manager.js` |
| 12 | `users[-1]` last-client routing | **Fixed:** explicit `pc_clients` / `cm_clients` dicts in `ClientRegistry` | `py/backend.py` |
| 13 | Unauthenticated `/ps/*` routes | **Fixed:** Bearer token required on every `/pc/*` route; token from private file | `py/backend.py` |
| 14 | Default password `12341234` (remote connection) | **Fixed:** no default password anywhere; missing/empty token file refuses to serve | `py/config.py`, `py/backend.py` |
| 15 | `git reset --hard` update command | **Removed:** no git operations anywhere in this repo | — (no git calls) |
| 16 | Automatic `pip install` on import failure | **Removed:** no pip calls; `pyproject.toml` declares zero runtime dependencies | `pyproject.toml` |
| 17 | Installer requesting admin rights | **Fixed:** `install.py` / `uninstall.py` do only path checks + copy/link + `config.json`; never elevate | `install.py`, `uninstall.py` |
| 18 | Opaque binary `.ccx` plugin package | **Removed:** no binary package; panel is plain HTML/JS/CSS | `photocraft_panel/` |
| 19 | Photopea integration | Not ported: Photopea is Photoshop-specific; PhotoCraft file exchange covers PNG/PSD instead | — (deliberate omission) |
| 20 | Built-in SD1.5 workflows (5 localised variants) | 5 workflows: `pc_sd15_txt2img`, `pc_sd15_inpaint`, `pc_sd15_controlnet`, `pc_sd15_upscale`, `pc_sdxl_txt2img`, each with `en-US / zh-CN / zh-TW / ja-JP / ko-KR` prompt placeholders in `_meta`, standard ComfyUI node types only | `data/workflows/` |
| 21 | rgthree Fast Groups Muter workflow switching | **Equivalent:** `PhotoCraftManager.loadWorkflow()` + `setRenderMode()` (txt2img / inpaint / controlnet / upscale); no rgthree dependency | `js/manager.js` |
| 22 | Crop Over Selection / Preserve Selection / Play on Channels | Equivalent options: `crop_to_selection`, `preserve_selection`, `play_on_channels`, `margin`, selection mode new/add/subtract/intersect | `js/manager.js`, `photocraft_panel/app.js` |
| 23 | ComfyUI Cloud connection | Not ported: local-only by design; no cloud account / API key in this plugin | — (deliberate omission) |
| 24 | Port switching / queue / progress forwarding | Backend host/port in Settings + `sendQueue()` + progress forwarding in manager | `js/connection.js`, `js/manager.js`, `photocraft_panel/app.js` |
| 25 | Apply result back to the editor | Panel **Apply back to PhotoCraft** → `POST /pc/command` (`import_result`); adapter `import_result()` stages + `photocraft-cli run --place` in file mode | `photocraft_panel/app.js`, `py/photocraft_adapter.py` |
| 26 | File exchange (`PS_canvas.png` / `PS_mask.png` / `config.json`) | Same shape, renamed: `PC_canvas.png` / `PC_mask.png` / `config.json` in `data/pc_inputs/` | `py/nodes.py`, `py/photocraft_adapter.py` |
| 27 | License MIT + extra terms (Other) | **Changed:** standard MIT only, no additional terms | `LICENSE` |
| 28 | PhotoCraft adapter (new, no reference equivalent) | `PhotoCraftAdapter`: file mode (`photocraft-cli convert/info/run`) + live mode (TCP JSON-lines: auth, `engine.execute`, `ui.inspect`, `ui.screenshot`; 60 s timeout with not-run vs dispatched distinction) | `py/photocraft_adapter.py` |

## Deliberate omissions (with reasons)

* **Photopea integration** — Photoshop-specific; not applicable to PhotoCraft.
* **ComfyUI Cloud** — the reference's cloud path was unverified and needs an
  account; this plugin is local-only by design.
* **WASM filter plugin for the panel** — PhotoCraft WASM plugins have no
  network, so they cannot host the panel; the panel stays an external
  side panel by design.
