KOOLKID AI INTELLIGENCE — USER TRIAL FINAL PATCH
================================================

WHAT THIS PATCH FINISHES
- Human Apostle keeps its existing verified strategy rules:
  M15 execution, H4 bias, completed candles only, confirmed fractal structure,
  trendline break -> protected structure break/MSS -> later retest -> rejection -> entry.
- Adds real server-side continuous AI Auto-Trading for DEMO MT5 accounts.
- The scanner keeps running when the browser closes or the user logs out.
- Enabled scanners restore after the MT5 bridge restarts.
- Reconnect/wait behavior: if the selected account disconnects, the scanner stays enabled,
  reports WAITING, and keeps checking until the account is available again.
- Fresh completed-candle signals only.
- Persistent duplicate-signal protection shared by manual AI execution and auto execution.
- A signal is marked before order submission so an ambiguous broker/IPC response cannot cause
  the same completed-candle signal to fire twice.
- Live-account AI execution remains hard locked. The backend verifies MT5 trade_mode from the
  authoritative per-account worker; it does not trust a cached UI label.
- Adds AI Auto-Trading monitor/status/events to AI Intelligence.
- Keeps Copy Trades From Anywhere separate and unchanged.
- Keeps Deriv, Copy Trader, EA worker, Manual Trading, Accounts, Positions and strategy rules unchanged.

FILES REPLACED
mt5_module/mt5_bridge/main.py
mt5_module/mt5_bot/src/pages/AIPage.tsx
mt5_module/mt5_bot/src/services/aiControlService.ts
mt5_module/mt5_bot/src/types.ts

NEW TEST FILE
mt5_module/mt5_bridge/ai_trial/test_auto_trader.py

INSTALL
1. Stop KOOLKID / MT5 services.
2. Back up your current mt5_module folder.
3. Extract this ZIP into:
   C:\Users\jjmje\Desktop\deriv-bot-site
   and allow Windows to merge/replace the matching files.
4. Rebuild the MT5 frontend:

   cd /d C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_bot
   npm run build

5. Start KOOLKID normally with START_KOOLKID.bat.
6. Open MT5 BOT -> AI Intelligence.
7. Connect a DEMO MT5 account.
8. Choose account, symbol and fixed lot.
9. Run Apostle Scan once if you want to inspect the current state manually.
10. Click Start AI Auto-Trading.

USER-TRIAL SAFETY
- DEMO only. Live AI execution is blocked by the backend.
- No martingale, grid or averaging-down behavior was added.
- No EX5 decoding was added.
- No unfinished candle is used.
- No same-candle shift + retest is allowed.
- No duplicate execution of the same completed-candle signal.
- Copy Trades From Anywhere remains a separate feature using the existing copy engine.

TESTS RUN HERE
- Python compile of patched bridge main.py: PASS
- Existing Human Apostle tests: 8/8 PASS
- New duplicate-signal execution safety test: PASS
- Workspace isolation regression check: PASS
- CORS preflight for /api/mt5/ai/auto: OPTIONS 200 + correct local origin header
- Unauthenticated protected request: GET /api/mt5/ai/auto -> 401 PASS
- Changed TypeScript/TSX syntax parse: PASS

NOTE ABOUT FRONTEND BUILD
A full npm dependency install was not available in this isolated build container, so run
`npm run build` in your existing project where your normal node_modules/dependencies are installed.
The changed TS/TSX files passed TypeScript syntax parsing here.
