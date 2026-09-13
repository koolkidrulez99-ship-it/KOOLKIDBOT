# KOOLKID MT5 drop-in merge instructions

## Goal

Keep the existing Deriv bot and MT5 feature separate in source and execution. The MT5 Hub should be opened from the existing logged-in homepage using a new **MT5 BOT** button.

## Final main-bot layout

```text
deriv-bot-site/
├─ server.py                 # existing Deriv app; tiny Blueprint registration only
├─ templates/index.html     # existing homepage; one MT5 BOT button + tiny JS nav function
├─ static/                   # existing Deriv files; do not move MT5 source here
├─ strategies/               # existing Deriv logic; do not change
├─ deriv_engines/            # existing Deriv logic; do not change
├─ mt5_bot/                  # copy this supplied frontend folder here unchanged
├─ mt5_bridge/               # copy this supplied Windows bridge folder here unchanged
├─ mt5_web.py                # copy this supplied Blueprint here unchanged
├─ SETUP_MT5_BRIDGE.bat      # Windows local helper
└─ START_MT5_BRIDGE.bat      # Windows local helper
```

Do **not** merge `mt5_bridge/requirements.txt` into the existing root `requirements.txt`. The MetaTrader5 Python package is Windows-terminal-specific and must remain a separate environment/service.

## Homepage insertion point found in the supplied main bot

In `templates/index.html`, the existing homepage currently has the logout link followed by:

```html
<button id="koolkidAutoTradeLaunchBtn" class="koolkid-auto-trade-launch" type="button" onclick="openKoolkidAutoTradePlaceholder()">
    KOOLKID AUTO TRADE
</button>
```

Add the new button immediately beside/after it, reusing the same class so no redesign is required:

```html
<button id="mt5BotLaunchBtn" class="koolkid-auto-trade-launch" type="button" onclick="openMt5BotHub()">
    MT5 BOT
</button>
```

Near the existing `openKoolkidAutoTradePlaceholder()` function, add:

```javascript
function openMt5BotHub(){
    try{
        sessionStorage.setItem("skipDisconnectOnce", "1");
    }catch(_err){}
    window.location.href = "/mt5-bot";
    return false;
}
```

The `skipDisconnectOnce` behavior is important because the existing homepage already uses it for internal navigation and page-exit disconnect protection.

## Flask registration

After the existing authentication helper functions (`login_required`, `is_admin`) are available, import/register:

```python
from mt5_web import create_mt5_blueprint
app.register_blueprint(create_mt5_blueprint(login_required, is_admin))
```

Do not copy MT5 route implementation into `server.py`. Keep the route in `mt5_web.py`.

## Build the MT5 frontend for /mt5-bot

Inside `mt5_bot/`, create a production env based on `.env.integration.example`. For a local Windows test with the bridge on the same laptop, use its bridge values.

Then:

```bash
npm ci
npm run build
```

The supplied Vite config supports:

- `VITE_ROUTER_BASE=/mt5-bot`
- `VITE_ASSET_BASE=/mt5-bot/`
- `VITE_HOST_HOME_URL=/`

This makes the React app live under `/mt5-bot` and adds a **Back to KOOLKID** control when integrated.

## Hosting warning

The local bridge at `127.0.0.1:8000` is for Windows/local use. Do not install `MetaTrader5` into a Linux/Render Deriv web process. Production multi-user real MT5 requires separate reachable Windows MT5 workers. Until that exists, keep deployed MT5 execution in simulation or point the frontend/API proxy at authorized Windows workers.

## Files Codex is allowed to modify in the existing main bot

Prefer only:

1. `templates/index.html` — add MT5 BOT button + `openMt5BotHub()` navigation function.
2. `server.py` — import/register supplied Blueprint.
3. Deployment/build config only if necessary to build/serve `mt5_bot/dist`.

Codex should not refactor existing Deriv routes, OAuth/PAT logic, strategies, profiles, WebSockets, trading execution, database code, or existing homepage behavior.
