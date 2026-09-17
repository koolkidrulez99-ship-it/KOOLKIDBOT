KOOLKID AI TRIAL — SESSION 3

This is a cumulative Session 3 package. It includes the Session 1 + Session 2 trial changes, plus Session 3.

SESSION 3 MAIN ADDITION
Copy Trades From Anywhere toggle inside AI Intelligence.

What it does
- Uses your existing Copy Trading master/slave link.
- Watches the connected Master account itself, not just trades placed from KOOLKID.
- When ON, any eligible NEW trade that appears on the Master can be copied automatically to linked slaves.
- That includes trades opened from MT5 desktop, MT5 mobile, WebTerminal, EA, VPS, another bot, or another trading app, as long as the position appears on the same connected Master MT5 account.
- Uses the current Copy Trading lot mode/settings.
- Existing open positions are ignored when the toggle is switched on. Only newly detected positions are eligible.
- Turning the toggle OFF keeps the copy link but returns it to the normal approval-popup mode.

Important
- First configure a Master and one or more Slaves on the existing Copy Trading page.
- All selected accounts must remain connected to the multi-account worker.
- A trade on a completely different account/platform cannot be detected unless it appears on the connected Master account.

Other safety improvement
- The Human Apostle demo execution now blocks executing the exact same completed-candle signal twice.
- Apostle execution remains DEMO-ONLY in this trial.

FILES CHANGED
- mt5_module/mt5_bridge/main.py
- mt5_module/mt5_bridge/ai_trial/*
- mt5_module/mt5_bot/src/pages/AIPage.tsx
- mt5_module/mt5_bot/src/services/aiControlService.ts
- mt5_module/mt5_bot/src/types.ts
- mt5_module/mt5_multi_account/copy_engine.py

INSTALL
1. Back up your current mt5_module.
2. Extract this ZIP into:
   C:\Users\jjmje\Desktop\deriv-bot-site
3. Allow Windows to replace the matching files.
4. Rebuild the frontend:
   cd /d C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_bot
   npm run build
5. Restart KOOLKID, including the MT5 multi-account/copy worker, so the new copy-engine behavior is loaded.
6. Reload the browser page.

TEST COPY TRADES FROM ANYWHERE
1. Go to Copy Trading and make sure a Master + at least one Slave are linked.
2. Go to AI Intelligence.
3. Turn ON Copy Trades From Anywhere.
4. Open a NEW small DEMO trade on the Master from somewhere outside KOOLKID, for example MT5 mobile or the normal MT5 terminal.
5. The linked Slave account should receive the copied trade automatically.
6. Close or modify SL/TP on the Master and verify the existing copy engine mirrors those actions according to its current behavior.

Use demo accounts first while testing Session 3.
