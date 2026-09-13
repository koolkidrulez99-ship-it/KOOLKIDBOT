# Demo Test Progress

Status: incomplete, awaiting another user login/demo connection. User confirmed the $266.22 intervening loss was their own activity, which was excluded. Continued at 05:49-06:06 UTC on September 9, then paused. At 15:27 UTC both the server and Chrome were closed. Restarted the unchanged local app and opened its login page in the Codex in-app browser. See `checkpoint.json` for current browser, server, limits and resume instructions.

Latest checkpoint: **32 test contracts placed and settled, 14 wins, 18 losses, -$1.92 net**, all actual stakes $0.35 (gross stakes $11.20). Last test balance $47,587.13. All test auto modes were stopped. Carry 40 active minutes used (rounded up), leaving 20 minutes and $8.08 of net-loss allowance. A new connection must not reset these limits.

This is a live functional test, not a historical backtest or evidence of future profitability.

## Limits and Checkpoint

- Authorized: minimum stakes, up to 60 minutes of testing, maximum 10 currency units net demo loss. Never trade a real account.
- Verified account during the completed run: USD demo, PAT connection, masked suffix `8303`.
- First trade test: 2026-09-08 14:31:18 UTC. Last completed live case: 14:42:41 UTC. Paused after switching to KOOLKID at 14:43:02 UTC.
- Starting balance: $47,855.27. Last completed test balance: $47,587.13, after excluding the user-confirmed $266.22 unrelated loss during a pause.
- 32 test contracts placed and settled; 14 wins, 18 losses; net **-$1.92**, total stakes $11.20. Every actual purchase used $0.35. The authorized loss limit is net, not gross stakes.
- No observed contracts remained unsettled at the checkpoint. Automatic HUMAN test loops were stopped before switching profiles.
- Carry the $1.92 test loss and 40 minutes of active testing (rounded up) into the next continuation. Do not count an intervening deposit, withdrawal, or unrelated user trade as test P/L. 20 minutes remain; pauses do not grant a new full window.
- The original wall-clock window has elapsed. Establish the remaining active-test window only after the user reconnects; do not reuse the old browser recorder's expired deadline or assume old budgets remain enabled.

## Findings

### 1. HUMAN Settlement Metadata Is Reused From Older Trades

Live evidence: 10 of 20 settlement events disagreed with their placement metadata. Fields affected include direction, contract type, mode, batch ID, and dual-market leg index.

For example, contract `12164304419` was placed as CALL/RISE in batch `HUMAN-RF-1788878091849-50`, but its settlement was emitted as PUT/FALL with the previous batch ID `HUMAN-RF-1788878088363-2497`. The Rise/Fall martingale's displayed session P/L remained at -$0.04 while later pairs settled. Further pairs were started through the timeout fallback, so continuing to buy does not mean the accounting and progression are correct.

Relevant source: `server.py:20958` accepts an expired/open response with profit as settled. `strategies/human.py:797` rejects that status unless other terminal indicators exist. `server.py:21153` then retrieves the previous trade entry and fills metadata with `setdefault`, preserving stale fields. Current contract ID/profit are overwritten onto that older entry.

An isolated, no-network reproduction confirmed the incompatible settlement criteria and stale entry. The fixture represents an expired/open response; the complete original broker contract frame was not captured, so the exact trigger flags of each live event remain unverified.

### 2. UNCHAIN Higher/Lower Still Fails

Independently tested Higher, Lower, and Both on Step Index 100, five ticks, $0.35 per leg, signed barriers +0.10/-0.10. All returned HTTP 400 with `Invalid barrier. ContractBuyValidationError`; no buys were placed. Both aborted when its Higher proposal failed.

The final explicit Higher payload preserved the sign and market precision:

```json
{"amount":0.35,"barrier":"+0.1","basis":"stake","contract_type":"CALL","currency":"USD","duration":5,"duration_unit":"t","proposal":1,"req_id":248661855,"underlying_symbol":"stpRNG"}
```

Deriv returned `ContractBuyValidationError`, subcode `InvalidBarrier`, message `Invalid barrier.`, with `details.field` equal to `barrier2`. Full sanitized responses and echo requests are in `protocol.jsonl`.

The selected Step tick contract advertised barrier `+0.0`, but the local validator accepted the nonzero barrier and sent a proposal that Deriv rejected. On Volatility 10, +0.10 was blocked locally with a message saying +0.072 was supported. Retesting Higher with exactly +0.072 still produced Deriv's invalid-barrier error.

Background UNCHAIN quote requests also sent unsigned absolute-price barriers such as `7642.4` and `4797.059`. These were quote requests, not purchases. The initial capture contained 526 unique errored proposal IDs; the expanded, test-window-filtered capture now contains 1,426 across explicit tests and background quoting. These counts are not failed purchases. Do not attribute every background quote to a clicked trade button.

### 3. Market Switching Can Stall Ticks

Switching HUMAN to Step produced `You are already subscribed to stpRNG`. Later, switching the main UNCHAIN market to Step left the recorder's tick count unchanged and the health status recovering. The existing emergency reconnect endpoint restored the same demo account and live ticks in approximately four seconds without the user re-entering the PAT.

Tick-health status also fluctuated during UNCHAIN polling. `server.py:18470` restarts warmup even when a subscription already exists, and the UNCHAIN status route calls that helper. A full network-failure/reconnect soak test remains unperformed.

### 4. Even/Odd Errors and P/L Display

Step Index rejected Even/Odd as unavailable before buying. The panel nevertheless retained `Pending: EVEN + ODD` until Stop was used. On Volatility 10, two complete Even/Odd rounds bought and settled successfully at minimum stakes.

The configured $0.15 SL stopped the loop when one leg brought interim realized P/L to -$0.39; the second leg subsequently settled, leaving -$0.08. The panel displayed unsigned amounts (`SL reached at $0.39`, `Session P/L $0.08`), hiding the loss sign. The per-leg stopping behavior is an observation, not assumed to be a defect without confirming the intended pair-level risk semantics. The sign loss is visible in `static/js/profiles/human.js:1023` and `:1261`, which use the unsigned money formatter.

### 5. HUMAN Special-Contract Availability Is Blocked

`GET /human_manual_contracts` on Volatility 10 returned HTTP 400, `There's no contract available for this symbol.`, disabling High Tick, Low Tick, Only Ups/Downs, and Asian pair controls. The authenticated connection's `contracts_for` response did contain applicable contract types. The special-contract helper uses a separate legacy public WebSocket and uppercases symbols (`bot_modules/human_manual_contracts.py:13`), so this is a separate availability path to investigate. Those disabled contracts were not force-bought.

### 6. Cloud PAT Runtime Is Unsafe to Start As Currently Written

Source inspection found `_ensure_cloud_runtime_for_state` classifies any non-OAuth source as `legacy`, including PAT (`server.py:4161`). An isolated execution of that actual function with a fake token and a stubbed worker confirmed source mode PAT becomes worker mode legacy. No network calls occurred.

Cloud was not started: testing it live would risk sending the PAT through the obsolete legacy authorization path. Its copied runtime also needs account identity and risk-limit validation before a later demo run. This finding does not mean OAuth was changed or tested live.

### 7. JOKERJOE MATCH Batch Timed Out During a Stalled Connection

At 01:17:38 UTC, PLACE BATCH requested three independent DIGITMATCH proposals for digits 7/8/9 on R_10, one tick, $0.35 each. Each backend proposal waited five seconds and timed out, sequentially. No proposal IDs, buys, placements or balance changes resulted. The UI reported Stopped before the backend finished all three timeouts. Tick delivery had already stalled before the batch click, so the batch is not established as the cause of the subsequent disconnect.

At 01:21 UTC the socket was disconnected and automatic reconnect remained pending. The existing emergency reconnect action restored the saved PAT demo session, authenticated balance and healthy ticks in approximately nine seconds, without reading or re-entering the PAT. A duplicate R_10 subscription warning was emitted. No application code was changed.

## Continuation Results

- KOOLKID Take 3 Under: three buys and settlements, one win/two losses, net -$0.39.
- KOOLKID Burst 4 Over: four buys and settlements, four losses, net -$1.40.
- KOOLKID single martingale: OVER 5 at $0.35 won $0.48; configured $0.10 TP stopped the loop. Multiplier was 2 but maximum stake was capped at $0.35, so escalation was not exercised.
- KOOLKID trade-history snapshot: seven then-completed contracts retrieved with unique IDs, correct type/profit, no pending entries. The eighth trade occurred afterward.
- KOOLKID and JOKERJOE master AUTO: each toggled on for 30 seconds and back off successfully, with no buys. This verifies toggles, not signal-triggered execution or the many named auto strategies.
- JOKERJOE Differs: one buy/settlement, +$0.02.
- JOKERJOE MATCH 7/8/9: failed proposals/timeouts as described above; do not count these as purchased contracts or repeat this completed attempt.
- All purchased test contracts were settled, test loops off, before the second pause at 01:23:07 UTC.

### Latest Continuation, 05:49-06:06 UTC

- Fresh authenticated R_10 contracts_for advertised ONETOUCH and NOTOUCH at 5-10 ticks and relative barrier +0.160.
- Mutant Touch alone: bought/settled $0.35, loss -$0.35. No Touch alone: proposal timeout, no purchase. Both: two independent purchases settled, Touch +$0.47 and No Touch -$0.35. Combined Mutant P/L -$0.23.
- Mutant background quotes repeatedly used unsigned absolute barriers such as `4804.688` with five-tick contracts, producing InvalidBarrier errors. These are distinct from clicked purchases using the signed +0.160 barrier. `_request_ntt_proposal_quote` calls the shared barrier resolver (`server.py:8982`); the purchase and quote paths differ.
- Mutant Auto SL tried to sell tick Touch/No Touch contracts and received `Resale of this contract is not offered.` No successful early sale was observed.
- Mutant AUTO panel did not open after clicking its AUTO button. Panel computed display remained `none`, inline style remained absent, no page error was emitted. AUTO was never started; hidden controls were not forced.
- Cloud read-only status and UI rendered; worker was stopped, no open contract. Cloud PAT live start remains blocked by the earlier mode-classification defect.
- KOOLKID Luck toggled on for 40 seconds and off, no buys; signal-triggered execution remains unverified.
- JOKERJOE kidGx toggled on for 24 seconds and off, but five repeated `Proposal timeout` errors occurred and no buys. Source inspection shows the socket message callback directly calls `handle_on_message` (`server.py:21673`), which invokes `run_auto_trade` (`server.py:20916`). That calls synchronous `send_buy` (`server.py:17091`), whose digit proposal helper waits up to five seconds (`server.py:1161`) for responses delivered on that same reader. This is a likely blocking-response cause supported by the live five-second timeout pattern; a focused offline reproduction remains to be added before calling the diagnosis fully verified.
- Repeated spontaneous disconnects left automatic reconnect pending. The existing emergency reconnect action recovered the saved demo session each time without re-entering the PAT. No authentication source changes were made.
- All 32 observed purchased contracts had settlement events before the pause; no further purchases occurred in the final named-auto checks.

## Coverage

| Area | Observed Result |
| --- | --- |
| PAT demo connection/account selection | User connected; demo metadata, balance, and ticks verified |
| HUMAN Step Rise Now | One contract placed/settled; barrier-free CALL proposal |
| HUMAN Step Fall Now | One contract placed/settled; barrier-free PUT proposal |
| HUMAN Auto Rise & Fall | Two independent contracts placed/settled; stale result metadata observed |
| HUMAN Do Both | Five pairs placed/settled; P/L/batch matching fails; manual stop exercised |
| HUMAN Dual Markets, same Step market | Both legs placed/settled; second settlement carried first-leg metadata |
| HUMAN Even + Odd, Step | Availability rejection; no purchase |
| HUMAN Even + Odd, Volatility 10 | Two pairs placed/settled; SL stop and unsigned loss display observed |
| UNCHAIN Step Higher / Lower / Both | Independently attempted; all blocked by Deriv errors |
| UNCHAIN Volatility 10 Higher | +0.10 rejected locally; advertised +0.072 rejected by Deriv |
| Reconnect with no open test positions | Same demo restored; fresh OTP success, WebSocket open and balance logs captured |
| Existing test suite | 365 passed, 12 existing deprecation warnings, before live testing |
| New offline reproductions | HUMAN stale-entry criteria and Cloud PAT-to-legacy classification reproduced |
| KOOLKID | Take 3, Burst 4, TP stop and history passed; master-auto toggle only |
| JOKERJOE | Differs passed; MATCH batch timed out; master-auto toggle only |
| Mutant | Touch and Both purchased/settled; standalone No Touch timed out; AUTO panel blocked; Auto SL resale rejected |
| Cloud | Live start blocked by the PAT runtime defect |

The Rise/Fall multiplier remained configured at 2, but maximum stake was capped at $0.35. Even/Odd multiplier was set to 1. Consequently, live stake escalation and both-loss doubling are **not verified**. HUMAN TP-triggered stopping, dual-market martingale cycles, rare/loss sequences, partial-buy rejection, duplicate Connect, account switching, OAuth login, full page-reload history persistence, forced network loss, sell/early close, and the remaining named auto strategies are also not certified by this run.

Inventory covers 158 routes and all six component files, including hundreds of controls. An inventory is not execution coverage. Do not call this a complete bot backtest or report unexercised strategies as passing.

## Resume Order

1. Login page is open in the Codex in-app browser, tab 1. User will sign in and connect demo. Do not read credentials, cookies or browser storage; old Chrome CDP is no longer running.
2. Verify demo metadata, current balance, no running strategies/open positions and healthy ticks. The earlier $266.22 difference was confirmed unrelated; ask only about any further change from $47,587.13. Restore bounded test budgets after reconciliation.
3. Set a 20-minute remaining active-time window and carry forward $1.92 test loss; do not reset cumulative test P/L.
4. Finish reconciliation and only additional safe unexercised cases within limits. Do not repeat completed successful or failed cases. Investigating findings does not authorize bot source fixes.
5. Inspect Cloud's UI without starting its PAT worker; leave live Cloud trading blocked pending an explicitly authorized fix and safety verification.
6. Finish safe disconnect/cleanup, reconcile actual trades and balances, and update this report with pass/fail/blocked/unexercised distinctions.

## Files Added

All changes are confined to `reports/demo-test-2026-09-08/`. No bot source, authentication route, strategy, or UI implementation was edited. `git diff --stat` remains empty for tracked application files.

- `control.cjs`: demo-verified browser test recorder and bounded test actions.
- `evidence.jsonl`: sanitized UI, route-response, placement, settlement, and checkpoint records.
- `collect.cjs` / `protocol.jsonl`: allowlisted, sanitized Deriv protocol extraction from existing server logging. OTP URLs and credentials are not retained.
- `inventory.py` / `inventory.json`: route and UI-control inventory.
- `reproduce_findings.py` / `offline-reproductions.json`: no-network reproductions of the two code-level defects.
- `summarize.cjs` / `summary.json`: deduplicated counts, balances, and placement/settlement metadata comparisons.
- `REPORT.md`: this progress report and continuation checkpoint.
- `checkpoint.json`: current login handoff, remaining limits and resume instructions.
