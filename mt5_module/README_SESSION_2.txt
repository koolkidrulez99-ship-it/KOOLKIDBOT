KOOLKID AI TRIAL — SESSION 2

What this session adds
- Keeps the Human Apostle scan from Session 1.
- Adds a demo-only execution path from the AI Intelligence page.
- Uses the current Apostle signal's direction, SL, and TP.
- You choose a fixed lot size in the UI.
- Live MT5 accounts are blocked. Demo accounts only.

Files in this session
- mt5_module/mt5_bridge/main.py
- mt5_module/mt5_bot/src/pages/AIPage.tsx
- mt5_module/mt5_bot/src/services/aiControlService.ts
- mt5_module/mt5_bot/src/types.ts
- mt5_module/mt5_bridge/ai_trial/*

How to test
1. Copy these files into your project.
2. Rebuild the MT5 frontend if needed.
3. Start your normal bridge/bot stack.
4. Open AI Intelligence.
5. Run Apostle Trial Scan.
6. If the current result is BUY or SELL, select a demo MT5 account and click Execute demo trade.

Safety
- Session 2 blocks live accounts.
- It will only execute when the current scan has a live BUY or SELL proposal.
- It still does not add full risk sizing yet; it uses the fixed lot size you enter.
