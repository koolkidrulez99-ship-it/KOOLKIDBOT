# AI review fixes

These changes preserve the newer MT5 live-confirmation controls already present
in the working tree. Live AI execution still requires explicit confirmation;
the earlier handoff's description of a hard demo-only lock was out of date.
No real-money or demo broker orders were placed during this review.

## Corrected behavior

- The main dashboard's older signal monitor tracks break/shift timestamps, so
  rolling candle windows cannot prevent a later retest. Signals are not reported
  as executed positions and do not leave the monitor permanently managing a
  nonexistent position.
- Both Apostle analyzers require current execution structure to agree with the
  trade, reject malformed OHLC data, and expire old setups. The MT5 analyzer
  applies only H4 candles completed at the evaluated M15 candle's close, avoiding
  future bias leaking into historical evaluations.
- Confidence thresholds are enforced in the older monitor. Its score reports
  verified structure/retest/confirmation factors; it no longer awards invented
  momentum/volatility points. Lot sizing floors decimal values to the broker
  step, including after the maximum-volume cap.
- Older monitor EX5 requests use stored, user/account/symbol/timeframe-bound
  server analysis and reject stale analyses. Browser-provided approval objects
  and account equity cannot authorize a signal.
- The older backtest waits for an open trade to resolve before another entry.
  Unimplemented historical bias backtests are explicitly rejected.
- Apostle execution rescans the setup before submission, verifies account mode,
  validates protective prices and size, honors a stop/settings change during a
  scan, and requires a confirmed MT5 fill response before reporting execution.
  Failed or ambiguous submissions remain consumed by the duplicate guard.
- Auto Select serializes its executions within each workspace and rechecks
  independently running presets, native position conflicts, account permissions,
  and automation configuration immediately before using the existing executor.
- The main monitor understands MT5's `symbol` field, preserves market selection,
  ignores late responses for changed controls/accounts, and reports unavailable
  MT5 data. Saving a teaching clears the correct form after the async request.

## Workspace linking for the older main-dashboard monitor

The existing MT5 Hub has its own authenticated workspace and needs no new
configuration. For the separate main-dashboard monitor, a shared global token
must never expose one MT5 workspace to every KOOLKID user.

Configure `AI_INTELLIGENCE_MT5_USER_TOKENS` as a server-side JSON object mapping
each authenticated KOOLKID username to that user's existing MT5 Hub bearer token.
The same mapping can be supplied through Flask application configuration.
Alternatively, for one user only, pair `AI_INTELLIGENCE_MT5_TOKEN` with
`AI_INTELLIGENCE_MT5_USER` naming its owner. Keep these values out of Git and
browser code. Expired MT5 tokens must be refreshed through the existing Hub
login. No second authentication system was introduced.

`AI_INTELLIGENCE_MT5_URL` and `AI_INTELLIGENCE_MT5_TIMEOUT` retain their existing
meanings. A missing mapping fails closed; the MT5 Hub's own AI page remains the
normal place to use its account and execution features.

## Files changed in this review

- `ai_intelligence/apostle.py`
- `ai_intelligence/routes.py`
- `ai_intelligence/mt5_provider.py`
- `ai_intelligence/intelligence_store.py`
- `ai_intelligence/REVIEW_FIXES.md` (new)
- `static/js/ai_intelligence.js`
- `static/css/ai_intelligence.css`: prevent the mobile panel extending beyond the
  viewport when a vertical scrollbar is present.
- `tests/test_ai_intelligence.py`
- `tests/test_ai_intelligence_apostle.py`
- `mt5_module/mt5_bridge/ai_trial/engine.py`
- `mt5_module/mt5_bridge/ai_trial/test_engine.py`
- `mt5_module/mt5_bridge/ai_trial/test_auto_trader.py`
- `mt5_module/mt5_bridge/ai_trial/test_execution_regressions.py` (new)
- `mt5_module/mt5_bridge/ai_auto_select.py`
- `mt5_module/mt5_bridge/test_ai_auto_select.py`
- `mt5_module/mt5_bridge/main.py`: AI-only helpers/status plus a `math` import.
- `.gitignore`: exclude the MT5 Hub signing secret and saved credentials.

Removed from Git tracking, but retained on disk:

- `mt5_module/data/mt5_hub_auth_secret`
- `mt5_module/mt5_multi_account/data/credentials/session-32321374.bin`

Their old copies remain in Git history. Rotate exposed credentials/signing
secrets before deploying if that history has been shared; no secret rotation or
history rewrite was performed, to avoid unexpectedly invalidating sessions.

## Verification and remaining limits

- Main AI suite: 97 tests passed.
- MT5 Apostle, execution safeguards, Auto Select and native Apostle preset
  tests: 36 passed, using the bridge's existing virtual environment.
- JavaScript syntax check passed. Browser teaching-form save/reset succeeded
  on an isolated dashboard with no console errors.
- Existing Python deprecation warnings remain unrelated to these fixes.
- Broker execution tests used mocked MT5 responses, not real orders. Actual
  broker fills, live account behavior and long-running deployments remain to be
  validated on a connected demo account.
- The older main-dashboard intelligence monitor remains signal-only. It
  explicitly reports that account risk/volume is not validated there. Its
  optional direct-engine sizing tests do not imply a connected sizing adapter.
- Historical multi-timeframe backtests, rejected-trade counterfactual outcomes,
  automatic teaching promotion and internet research remain unimplemented in
  that older monitor. The separate MT5 native features are preserved.
- Deriv trading/authentication, MT5 account/copy/EA workers, existing native
  strategy formulas, and their execution services were not modified.

Restart the KOOLKID and MT5 bridge servers when no orders are in flight to load
the Python changes. Static AI JavaScript is loaded on page refresh; the React
Hub bundle was not changed or rebuilt for this review.
