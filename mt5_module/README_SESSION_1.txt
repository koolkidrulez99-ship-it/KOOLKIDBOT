KOOLKID AI INTELLIGENCE — TRIAL SESSION 1 OF 3
================================================

PURPOSE
-------
This is a small trial patch, not the finished AI system.
It adds a real read-only Human Apostle scanner to the EXISTING AI Intelligence page.

SESSION 1 SCOPE
---------------
- Human Apostle trial only
- M15 execution timeframe
- H4 bias timeframe
- completed candles only
- confirmed fractal swings (2 candles left + 2 right)
- HH / HL / LH / LL structure labeling
- opposing trendline break detection
- protected-structure break / market-structure shift
- later-candle retest only (same candle is blocked)
- bullish/bearish rejection candle confirmation
- H4 alignment required before a BUY/SELL signal
- structural SL proposal + default 2R TP proposal
- transparent confidence factors
- saves the latest scan to mt5_bridge/data/ai_trial_state.json
- SIGNAL ONLY — it NEVER opens, modifies, or closes a trade

NOT IN SESSION 1 YET
--------------------
- automatic order execution
- risk-percent lot sizing
- Dear Bruce profile
- selectable independent timeframes
- multiple simultaneous AI strategy instances
- EX5 -> AI approval workflow
- learning/outcome database
- backtest dashboard
- natural-language teaching
- internet/news confirmation

Those are intentionally held for Sessions 2 and 3.

FILES IN THIS PATCH
-------------------
mt5_module/mt5_bridge/main.py
mt5_module/mt5_bridge/ai_trial/__init__.py
mt5_module/mt5_bridge/ai_trial/engine.py
mt5_module/mt5_bridge/ai_trial/storage.py
mt5_module/mt5_bridge/ai_trial/test_engine.py
mt5_module/mt5_bot/src/pages/AIPage.tsx
mt5_module/mt5_bot/src/services/aiControlService.ts
mt5_module/mt5_bot/src/types.ts

INSTALL
-------
1. CLOSE KOOLKID and the local MT5 services first.
2. Back up your current mt5_module folder.
3. Extract this ZIP into the ROOT of deriv-bot-site.
4. Allow Windows to MERGE the mt5_module folder and REPLACE the files listed above.
5. Do NOT delete your mt5_module/data folders or terminal folders.
6. Rebuild the MT5 frontend the same way you normally do:

   cd /d C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_bot
   npm run build

   If node_modules is missing, run your normal npm install/npm ci step first.

7. Start KOOLKID normally with your existing launcher.
8. Connect a DEMO MT5 account.
9. Open MT5 BOT -> AI Intelligence.
10. Select a connected account and symbol, then click RUN APOSTLE TRIAL SCAN.

WHAT YOU SHOULD SEE
-------------------
The page should show:
- M15 current structure
- trendline stage
- structure-shift stage
- later-retest stage
- H4 bias
- confidence + factors
- current decision, such as:
    SCANNING
    WAIT FOR TRENDLINE BREAK
    WAIT FOR STRUCTURE SHIFT
    WAIT FOR LATER RETEST
    WAIT FOR CANDLE CONFIRMATION
    BUY
    SELL
- entry / SL / TP only when every required stage completes on the latest completed candle

SAFETY / ISOLATION
------------------
This Session 1 patch does NOT modify:
- mt5_multi_account
- copy_engine
- EA worker
- EX5 execution
- Manual Trading
- Positions
- Accounts
- Deriv code/chart/OAuth/PAT/strategies

The only existing backend file changed is mt5_bridge/main.py, and that change only adds three /api/mt5/ai/trial routes plus the AI-trial import/request model.

TESTS RUN BEFORE PACKAGING
--------------------------
Python AI trial tests: 8/8 passed.
Python syntax compilation for main.py and ai_trial/*.py: passed.

The test environment here could not install the frontend npm dependencies, so the final React/Vite build must be run on your project where your node_modules/dependencies already exist. If that build reports an error, send me the exact output before moving to Session 2.

SESSION PLAN
------------
Session 1: trial scanner + UI (this ZIP)
Session 2: strategy profiles, risk sizing, independent selected timeframes, Dear Bruce, stronger persistence/logging
Session 3: EX5 AI approval/shadow flow, learning/outcome records, backtest foundation, final integration/testing

DO NOT MOVE TO SESSION 2 UNTIL YOU HAVE OPENED AI INTELLIGENCE AND TRIED THIS VERSION.
