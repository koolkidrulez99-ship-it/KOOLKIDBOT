# KOOLKID MT5 Multi-Account Drop-in v1

This is a **standalone testable module** for the future KOOLKID MT5 Hub upgrade.

## Included
- Up to 10 active MT5 accounts at the same time.
- One selected MASTER; all other connected accounts stay online.
- Connected accounts may be SLAVE or INDEPENDENT.
- One persistent Python process per account so MT5 sessions do not overwrite each other.
- Manual trade to selected accounts with symbol / BUY-SELL / lot / SL / TP.
- Master/slave copy engine for:
  - new positions,
  - SL/TP changes,
  - full closes,
  - all/manual/EA/specific Magic Number filtering,
  - same/fixed/multiplier/equity-proportional lot sizing.
- All-account Positions page with individual close buttons.
- `.ex5` trades can be copied because MT5 EA positions normally have a non-zero `magic` number.
- Passwords are not saved in `data/state.json`.
- Explicit simulation mode for safe testing. A failed real connection never silently becomes simulation.

## Architecture
The MetaTrader5 Python package has process-wide terminal/account state, so this module uses one worker process per account. For **real simultaneous accounts**, each account should have its own dedicated MT5 terminal instance/path.

## Test now
1. Run root `SETUP_MULTI_ACCOUNT.bat`.
2. Run root `START_MULTI_ACCOUNT.bat`.
3. Open `http://127.0.0.1:8002`.
4. Click **Create 3 SIM accounts**.
5. SIM 1 is master; SIM 2/3 are slaves.
6. Click **Start copying**.
7. Select only SIM 1 in Manual Trade and open a test trade.
8. The trade should appear on SIM 2 and SIM 3 shortly after.
9. Positions should show all open trades across all accounts.

## Later integration
Copy this folder into:

`C:\Users\jjmje\Desktop\deriv-bot-site\mt5_module\mt5_multi_account`

Then give Codex `CODEX_INTEGRATION_PROMPT.txt`.

Start with demo MT5 accounts for real tests.
