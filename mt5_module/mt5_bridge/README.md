# KOOLKID Local MT5 Bridge v4.2

This folder provides the real local Windows MetaTrader 5 bridge used by KOOLKID MT5 Hub.

## Real bridge capabilities

When running on Windows with MetaTrader 5 installed and a broker account connected, the bridge can use the official `MetaTrader5` Python package for:

- MT5 account login and live account metrics
- full broker symbol discovery (not just a fixed watchlist)
- live bid/ask quotes
- real MT5 candles
- open-position retrieval
- deal/history retrieval with individual net P/L
- manual market BUY/SELL orders
- individual position close
- close-all positions
- Hub Risk Center checks before manual orders
- copy-trading rule persistence/API

## Not enabled yet

- automatic `.ex5` EA deployment/launching
- simultaneous isolated MT5 terminal workers
- real multi-account copy execution
- remote/public bridge hosting
- Deriv options execution

The current bridge controls one active MT5 terminal session at a time. Real copy relationships can be configured/stored in the Hub, but they will not be falsely reported as live until an isolated worker exists for each participating account.

## Safety defaults

- Server binds to `127.0.0.1` only.
- Account passwords are used for the login request and are **not written to the KOOLKID bridge state file**.
- Demo trading is permitted when the terminal/broker allows it.
- Real-money execution requires KOOLKID's explicit testing-phase risk confirmation before a LIVE order or bot is started.
- Starting the bridge never opens a trade.

## Setup

1. Install your broker's Windows MetaTrader 5 desktop terminal and verify login manually.
2. Use a DEMO account first.
3. Run `SETUP_MT5_BRIDGE.bat` from the project root.
4. If auto-detection does not find the correct terminal, copy `mt5_bridge/.env.example` to `mt5_bridge/.env` and set `MT5_TERMINAL_PATH` to the exact `terminal64.exe`.
5. Run `START_KOOLKID.bat` from the project root. It starts the bridge, EA worker and main KOOLKID server separately.
6. The launcher opens the local KOOLKID URL automatically.
7. In KOOLKID, use **MT5 Accounts → Add MT5 Account → Test Connection → Connect Account**.

## Live-money confirmation

LIVE accounts are not demo-locked. Before KOOLKID submits a real-money order or starts a trading bot, the user must explicitly accept the testing-phase risk warning in the Hub. Broker/terminal permissions and Hub Risk Center rules still apply.
