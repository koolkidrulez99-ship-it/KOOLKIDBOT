# Implementation and audit

## Activation follow-up (2026-09-23)

The supplied global PAT is now stored encrypted in the ignored local research
database; its generated encryption key is preserved beside that database.
The existing PAT application ID was explicitly saved for this research service.
Live demo authentication succeeded. The restarted independent daemon reached
READY with 20 subscribed markets and all four strategy adapters, collecting ticks
and paper outcomes. No orders were placed. This supersedes the original
unconfigured/unverified activation notes below, not the sustained-load limitations.

Connections now reject real accounts and real OTP WebSocket URLs. Admin can save
a PAT App ID; Start/Reconnect can launch a missing daemon. Configuration and the
enabled/paused state persist across server restarts and source updates that retain
the private runtime directory. The default data path no longer depends on the
working directory. Browser closure has no effect on the daemon. Machine shutdown,
sleep and process crash recovery still require an always-on host/OS supervisor.

Research regression suite: **27 passed**, including local encryption persistence,
real-only account rejection and real WebSocket URL rejection. Local key/database
paths are confirmed excluded from Git. Existing trading and MT5 code was untouched.

## Files created

- `deriv_backtest/__init__.py`
- `deriv_backtest/__main__.py` (single-daemon OS lock)
- `deriv_backtest/store.py` (database and encrypted credential storage)
- `deriv_backtest/transport.py` (isolated PAT/OTP read-only transport)
- `deriv_backtest/strategies.py` (four research adapters)
- `deriv_backtest/statistics.py` (window aggregation and performance index)
- `deriv_backtest/engine.py` (collection, replay, paper outcomes, caches)
- `deriv_backtest/web.py` (authenticated read APIs, admin controls)
- `deriv_backtest/README.md` (configuration, scoring and deployment details)
- `deriv_backtest/IMPLEMENTATION_REPORT.md` (this report)
- `templates/backtest_tools.html`
- `templates/intelligence_admin.html`
- `static/css/backtest_tools.css`
- `static/js/backtest_tools.js`
- `static/js/intelligence_admin.js`
- `tests/test_deriv_backtest.py`
- `tests/backtest_browser_smoke.py`

## Existing files changed

- `server.py`: four-line route registration/daemon launch only.
- `templates/admin.html`: one isolated admin partial include.
- `templates/index.html`: Backtest Tools navigation link.
- `requirements.txt`: cryptography dependency for Fernet.
- `.gitignore`: exclude private runtime research directory.

No MT5 file was edited by this task. Pre-existing MT5 working-tree changes were
left alone. Existing Deriv execution, OAuth, PAT, profile, chart and cloud strategy
code was not edited. The strategy adapters call existing pure analysis helpers.

## Test results

Final `python -m pytest tests -q`: **643 passed, 3 failed**.
All **23 new research tests pass**. Existing PAT/OAuth regression tests pass.
The failures are pre-existing homepage expectations:

- `test_auth_login.py::test_login_accepts_email_identifier` expects `/` while
  committed code already redirects to `/deriv-bot`.
- `test_cover_page.py::test_anonymous_root_renders_cover_page` expects old cover text.
- `test_cover_page.py::test_authenticated_root_keeps_existing_dashboard` expects
  `index.html`, while committed code already serves `master_home.html`.

These unrelated expectations were not changed to make the suite green.

Headless Edge browser test passed using a temporary isolated Flask/database
fixture: desktop 1366px, tablet 768px, phone 390px; filter changes actually change
sample counts; details render; no document overflow; admin password masking and
five controls; no JavaScript runtime errors. Fixture data never enters production.
Python compilation, JavaScript syntax, and diff whitespace checks pass.

## Audit findings addressed

- Authentication: separate global environment/encrypted secret, separate Feed;
  no access to user credentials or execution server state. Admin role and CSRF
  checks; HTTPS required for remote secret submission. Secrets never returned.
- Trade safety: allowlist rejects real purchase/sell/authorize calls before any
  socket access. No live trading callback is available in the paper engine.
- Concurrency: tested two daemon processes; the second exits before networking.
  Tested 100 concurrent authenticated viewers without creating a feed.
- Database load: those 100 reads issue no tick-table queries. Atomic batches
  persist ticks, outcomes and totals; indexed recent outcomes restore window state.
- WebSocket: one reader and dedicated request IDs, finite timeouts, paced requests,
  bounded event queue, keepalive, exponential reconnect delay and fresh OTP.
- Accuracy: chronological replay; later-tick settlement; connection gaps cannot
  settle pending trades; no retroactive payout assignment; precision preserved.
- Windows: full detector lookback plus entry and exit must fit inside 50/100/200/500;
  ALL survives raw-data retention using cumulative outcomes. Tests prove different
  windows produce different statistics/scores.
- Caching: ten-second snapshots, explicit stale engine/cache and market indicators.
- MT5: no integration or service changes.

## Remaining limits and activation

No dedicated global PAT was supplied/configured in this task. Live account listing,
OTP connection, sustained all-market feed, provider limits and observed live payout
coverage remain unverified. No broker orders were placed. No production-readiness
claim is made without these checks.

Set `KOOLKID_INTELLIGENCE_APP_ID` and `KOOLKID_INTELLIGENCE_KEY`, restart KOOLKID,
then save the dedicated PAT and start collection in Admin. The README documents
all seven environment options and the alternative server-secret PAT.

Eligible markets are discovered from active symbols and contracts metadata,
including actual one-tick duration support. No live monitored-market count can
be reported before connecting. Four initial research adapters are integrated:
Under 9, Over 0, Golden Card, selective SAFE Differ. Other bots, full martingale/
session equity simulation, and authenticated broker verification remain future work.

The current singleton/storage design supports one execution host and shared local
persistent volume, not horizontally distributed hosts. Production requires process
supervision and backups. Historical payouts cannot be recovered from tick data;
unpriced samples retain outcomes but no fabricated EV or payout. Paper profit uses
cached observed indicative payouts and excludes execution costs/slippage.
