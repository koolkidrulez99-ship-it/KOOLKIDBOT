# Targeted Profile Fixes

The user stopped the full backtest. No further demo trades or broad regressions were run.

## Fixed

- HUMAN settlement: expired/open broker frames accepted by the server now reach the strategy as settled copies with the resolved profit. Old result entries cannot supply the next trade's direction, batch ID or dual-market leg. Current placement metadata determines the displayed symbol. Sequential duplicate settlements remain ignored.
- HUMAN special-contract controls: PAT availability now uses the connected session's active-symbol/contract metadata instead of a separate legacy WebSocket. Explicit-market manual orders no longer unpack a two-item lookup result as three items.
- HUMAN Even/Odd errors: unsubmitted legs no longer remain falsely pending after rejection. Confirmed contract IDs remain tracked if an error occurs after acceptance. Loss displays retain the minus sign. Stake progression and TP/SL thresholds are unchanged.
- KOOLKID/JOKERJOE AUTO execution: proposal and KOOLKID quote waits run outside the WebSocket reader. A single-flight lock prevents overlapping dispatches; queued work is rejected after profile, market, connection or session changes. Existing signal and trade functions are reused unchanged.
- Shared reconnect: only the reconnect scheduler owns the pending flag, preventing a failure handler from accidentally suppressing reconnect.
- Shared tick health: repeated checks of an existing or pending subscription no longer reset its warmup or duplicate the subscription.

## Verification

- 16 focused Python cases in `tests/test_scoped_execution_fixes.py`, run incrementally for each changed area.
- 3 executable JavaScript cases in `tests/test_human_parity_errors.cjs`.
- Coverage includes three successive HUMAN pairs, metadata integrity, duplicate settlement suppression, actual AUTO runner dispatch with simulated broker replies, next-trade execution, stale-context cancellation, reconnect deduplication, PAT contract availability, subscription polling, rejected parity orders and signed losses.
- All 19 checks passed. Two existing datetime deprecation warnings remain. No full bot regression was run.
- Local server restarted with the patched code on `http://127.0.0.1:5055/`; dashboard loaded successfully. User must reconnect PAT. No PAT was read or retained in test artifacts.

## Scope and Remaining Work

- Application files changed: `server.py` and `static/js/profiles/human.js`. Added the two focused test files named above. Updated this report and the stopped-backtest checkpoint.
- No strategy files, OAuth routes/authentication functions, PAT authentication functions, environment variables, other profile UI files, or engine files were edited. Shared execution/reconnect helpers necessarily affect their callers.
- These are fixes for the identified blockers, not certification of every button in the three profiles. Post-fix live broker execution, partial-buy/retry races, and longer unattended runs are not yet verified. No profitability claim is made.
- MUTANT, UNCHAIN, KidGx and Cloud-specific work remains out of scope. The old full-backtest instructions must not be resumed.
