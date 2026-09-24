# KOOLKID Backtest Tools

Deriv-only shared research service. It imports no server execution functions, user
session managers, PAT/OAuth state, or MT5 modules. Four initial adapters are active:
Under 9 ten-tick absence, Over 0 ten-tick absence, and the existing Golden Card
Over 1 / Under 8 confidence and loss guard, plus the selective SAFE Differ setup
detector. These are unit-stake setup observations, not whole-session reinvestment
or martingale simulations. Other strategies must be explicitly
registered and tested; they are not represented by invented results.

## Configuration and startup

- `KOOLKID_INTELLIGENCE_DIR`: persistent local directory; default
  `instance/deriv_intelligence`. Every web worker and the engine must share this
  directory. Keep it out of public/static folders and restrict OS access.
- `KOOLKID_INTELLIGENCE_APP_ID`: separate PAT-type app ID, or save a PAT App ID
  in Admin. There is no automatic fallback to the legacy or user app ID.
- `KOOLKID_INTELLIGENCE_KEY`: optional externally managed Fernet key. Generate
  once with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
  Store in deployment secrets, separately from the database. Do not rotate it
  without re-encrypting the saved credential. Without this variable, a key is
  generated once in `credential.key` beside the research database. Preserve that
  private file and the database across updates; losing the key loses PAT access.
- `KOOLKID_GLOBAL_DERIV_PAT`: optional server-secret alternative to saving the PAT
  in the admin form. An encrypted admin credential takes precedence.
- `KOOLKID_INTELLIGENCE_ACCOUNT_ID`: optional demo account from the global PAT.
  Real accounts and real WebSocket URLs are rejected, including explicit selection.
- `KOOLKID_INTELLIGENCE_RETENTION_DAYS`: raw tick retention, default 7 days.
- `KOOLKID_INTELLIGENCE_AUTOSTART`: default `1`. Flask launches a detached engine;
  OS file locking ensures only one process reaches networking per data directory.
  For production set to `0` and supervise `python -m deriv_backtest` with systemd
  `Restart=always` or Windows Task Scheduler/service recovery. The daemon is
  independent of browser lifetime. Admin Stop pauses collection, not the process.

Install requirements, restart Flask, open Admin > Global Deriv Intelligence,
save the dedicated PAT and PAT App ID, then Start Engine. The enabled setting is
persistent and resumed on server startup; an explicit Stop remains stopped.
The default data directory is anchored to the project, independent of launch directory.
Closing a browser does not stop collection. A powered-off or sleeping computer
cannot collect ticks. Server restarts launch the daemon; crash recovery and machine
startup without launching KOOLKID still require an OS supervisor. Test Connection
requests an authenticated balance response on the existing engine socket. No
user password or PAT is needed to view results after website login.

REST uses the official account list and fresh OTP endpoint on every reconnect.
The socket permits only market metadata, ticks/history, balance verification,
one-shot proposal observations and keepalive. `buy`, `sell`, `authorize`, and
unknown fields are rejected before socket access. WebSocket URLs and REST error
bodies are never logged or returned. Use HTTPS for remote admin access.

## Data and accuracy

SQLite WAL stores ticks (quote text, precision, digit, server/receive time, sequence
and connection), metadata, setups, paper outcomes, observed payouts, cached window
rankings and health. Writes are batched with cumulative totals in one transaction.
Indexes cover symbol/time, strategy/symbol/sequence, and window snapshots.
Raw ticks expire in bounded 10,000-row chunks; outcomes and cumulative statistics
are retained. ALL means all eligible observations recorded by this engine, not all
ticks ever produced by Deriv. Back up the database and its secret key separately.

Historical replay processes up to 500 provider ticks per market chronologically,
then live ticks feed the same paper evaluator. Setup and settlement must occur on
different ticks. Disconnects cancel unfinished paper observations rather than
inventing an outcome across a missing stream. Historical prices without historical
payout observations remain unpriced. No current payout is retroactively applied.

Finite windows require the complete detector lookback, entry and exit to lie in
the last N stored ticks of that symbol. ALL uses persisted cumulative statistics.
Windows select eligible observations, not a fresh rerun using different strategy
parameters. Ranking snapshots are rebuilt every 10 seconds; HTTP only reads these
small snapshots. Outcomes are indexed for bounded detail queries. Global stale
health/cache and per-market live flags prevent historical data masquerading as live.

Paper prices are indicative: a fresh observed one-unit proposal payout ratio is
usable for at most 60 seconds. Quotes are requested only near setups, at most once
every two seconds across the engine. No assumed payout or real contract purchase
is used. Paper results exclude execution slippage/rejections, latency and changes
in quotes at the exact entry. They must not be described as executable backtest P/L.

Score: `(60% EV index + 25% drawdown resilience + 15% losing-streak resilience)`
times sample weight `min(trades/100,1)` times priced-data coverage. The EV index is
`50 + 50*tanh(3*EV)`; drawdown resilience is `100/(1+DD/sqrt(priced trades))`;
streak resilience is `100/(1+longest losing streak/5)`. Score is not win probability.
Below 30 outcomes is INSUFFICIENT_DATA. VALIDATED requires 100 outcomes, 50 forward
outcomes, 95% priced coverage and positive EV; it means the sample gate passed, not
proof of a persistent trading edge. Unpriced datasets display no score or EV.

## Extending and validation

Add a `Strategy` to `strategies.REGISTRY`: stable/versioned ID, label, required
lookback, supported contracts, pure detector, duration. Detectors see past/current
digits only. Use only contract types supported by `evaluate`; add deterministic
tests for setup, duration and outcomes. Stateful strategies need a dedicated
research adapter with explicit reset/replay semantics; do not copy user runtime
state or call a live trading function.

`web.validate_setup` is a read-only future integration interface. Nothing invokes
it from existing manual or automated trading. It cannot execute orders.

## Deployment limits

This initial deployment is one execution host with a persistent local SQLite
volume; it is not a distributed multi-host leader election system. Do not deploy
independent copies with different data directories if one global engine is wanted.
Multi-host deployment needs a shared database and distributed lease first.
The bounded startup history is not a historical payout archive. Loss-of-process
recovery requires the deployment supervisor. Only four strategy adapters are integrated.
Real PAT/OTP connectivity and sustained provider load must be verified with a
dedicated global PAT; unit tests do not establish production readiness.
