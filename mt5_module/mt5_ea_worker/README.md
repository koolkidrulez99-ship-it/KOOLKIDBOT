# KOOLKID MT5 EA Worker

Local-only worker that installs uploaded `.ex5` and optional `.set` files into the selected MetaTrader 5 data directory and launches `terminal64.exe` with an official `/config:` startup file.

## Setup

Run `mt5_module\SETUP_MT5_EA_WORKER.bat`, then use the root `START_KOOLKID.bat` launcher. The worker must use a separate MT5 installation and data folder from the normal API bridge. Configure those with `MT5_EA_TERMINAL_PATH` and `MT5_EA_DATA_PATH` in `.env`; the worker rejects the bridge's paths.

DEMO EA execution is allowed. LIVE execution requires both explicit confirmation from the Hub and `MT5_ALLOW_LIVE_EA=1`. DLL imports remain disabled unless the Hub explicitly approves them and `MT5_ALLOW_DLL_IMPORTS=1` is configured.

Pause and resume are intentionally unavailable for arbitrary third-party EAs because MT5 provides no universal safe runtime pause contract. Stop terminates only the assigned terminal process and does not close broker positions.

Each production assignment is cloned into `data/terminals/<account>-<bot>` and launched in portable mode. Its process and assignment metadata live in the EA worker, so closing the KOOLKID browser does not stop it. A STOP request terminates only that assignment's terminal.

For a separate Windows execution server, configure the KOOLKID MT5 bridge with `MT5_EA_WORKER_URL` and configure the same strong random `MT5_WORKER_API_TOKEN` on both the bridge and EA worker. Bind `MT5_EA_WORKER_HOST` only to a private/VPN interface and firewall ports 8000-8002 from the public Internet. The EA worker rejects protected API requests without the bearer token whenever the token is configured.
