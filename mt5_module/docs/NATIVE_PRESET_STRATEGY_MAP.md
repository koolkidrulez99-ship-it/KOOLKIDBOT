# KOOLKID Native Preset Strategy Map

Status: source analysis blueprint before native runtime implementation.

## Architecture contract

- Built-in presets become native KOOLKID strategy modules. They do not launch EX5/MQ5 EAs and do not use the EA Worker on port 8001.
- User-uploaded MT5 files remain EA Worker jobs on port 8001.
- Native preset orders use the existing authoritative Multi-Account worker on port 8002.
- Preset names remain unchanged and system-owned/non-removable.
- Strategy translation must preserve the MQ5 rules, closed-bar timing, filters, setup expiry, risk controls, SL/TP, and trade-management behavior.
- AI Intelligence may select a strategy and rank valid setups, but it may not bypass that strategy's mandatory conditions.
- Human Apostle remains an independent strategy.

## Source availability

| Preset | Native source | Status |
|---|---|---|
| PRIMORDIAL BLACK | Primordial_Black.mq5 | Ready |
| PRIMORDIAL BLUE | Primordial_Blue.mq5 | Ready |
| PRIMORDIAL EMERALD | Primordial_Emerald.mq5 | Ready |
| PRIMORDIAL GOLD | Primordial_Gold.mq5 | Ready |
| PRIMORDIAL PURPLE | Primordial_Purple.mq5 | Ready |
| PRIMORDIAL RED | Primordial_Red.mq5 | Ready |
| PRIMORDIAL SILVER | Primordial_Silver.mq5 | Ready |
| PRIMORDIAL WHITE | Primordial_White.mq5 | Ready || BLACK ROCK | Black_Rock.mq5 | BLOCKED: MQ5 source not found |
| DEAR BRUCE PREMIUM | Dear_Bruce_Premium.mq5 | BLOCKED: MQ5 source not found |

The compiled EX5 files for BLACK ROCK and DEAR BRUCE PREMIUM are present, but they will not be reverse-engineered. Exact native ports require their MQ5 source or a complete written strategy specification.

## Shared Primordial behavior

The eight available Primordial sources are multi-timeframe price-action systems rather than simple indicator crossovers. They primarily use ATR for volatility, stop filtering, and risk sizing. Most use higher-timeframe bias, M15 setup logic, and M5 confirmation/entry.

Shared safety behavior includes spread filtering, percentage-risk sizing, daily drawdown limits, daily/symbol loss limits, one-trade-per-symbol controls, partial profit taking, break-even management, and ATR trailing. Native ports should expose only settings that exist in the source or are deliberately defined as KOOLKID runtime overrides.

## PRIMORDIAL BLACK

**Library title:** Liquidity Confluence Sniper

**Description:** Multi-timeframe liquidity strategy that combines sweep, displacement, Fair Value Gap and Order Block confluence, then waits for lower-timeframe rejection, micro break-of-structure and momentum before entry.

- Bias: H4 + H1 structure/trend, H1 liquidity behavior, premium/discount context.
- Setup: M15 liquidity sweep + displacement are mandatory.
- Zone: FVG, Order Block, or hybrid FVG+OB zone.
- Entry: M5 zone touch, rejection, micro BOS and momentum follow-through.
- Score: sweep 25, displacement 20, momentum 15, FVG 20, OB 20, hybrid bonus 10; entry threshold defaults to 70.
- Risk: 0.50% default; SL beyond swing/sweep/zone plus ATR buffer; default TP 2.5R.
- Management: partial at 1R, break-even near 1R, ATR trail from about 1.8R.
## PRIMORDIAL BLUE

**Library title:** Trendline Break & Retest Sniper

**Description:** Liquidity/FVG/Order-Block strategy with an independent M15 trendline-break module. It requires the broken trendline candle zone to be retested and respected on M5 before a trade can qualify.

- Base framework: same liquidity, displacement and FVG/OB family as BLACK.
- Trendline TF: M15; lookback 80 by default.
- Bull route: descending swing-high trendline breaks upward; bear route mirrors with an ascending swing-low trendline.
- Break zone: built from the trendline-breaking candle cluster.
- Retest: M5 must touch the break zone, hold the correct side of its midpoint, and reject/close strongly.
- Entry score: zone touch 20, rejection 20, BOS 15, momentum 10, trendline retest 25, trendline-zone touch 10, hybrid bonus 10 plus confluence bonus.
- Mandatory by default: zone touch, trendline break/retest, rejection, micro BOS and momentum.

## PRIMORDIAL EMERALD

**Library title:** Fibonacci Pullback Precision

**Description:** Liquidity-raid and displacement strategy built around deep Fibonacci pullbacks. It tracks the 61.8%-78.6% retracement zone, emphasizes the 61.8%-70.5% sweet spot, and waits for M5 price-action confirmation.

- Bias: H4 + H1.
- Setup: M15 swing liquidity raid followed within a short window by strong displacement.
- Fibonacci levels: 50%, 61.8%, 70.5%, 78.6%.
- Primary pullback zone: 61.8%-78.6%; sweet spot: 61.8%-70.5%.
- Entry: recent/fresh zone touch, sweet-spot touch, rejection, M5 micro BOS and momentum; 50% reclaim is an optional filter.
- Entry threshold: 75 by default.
- SL: beyond zone, raid extreme, 78.6 level and retest wick with ATR buffer.
- TP: default RR target or farther opposite liquidity, whichever extends the target in trade direction.
## PRIMORDIAL RED

**Library title:** Liquidity Raid Retracement Trader

**Description:** A purer liquidity-and-Fibonacci retracement model. It raids a recent M15 swing, demands displacement, then waits for price to revisit the 61.8%-78.6% retracement zone with rejection, structure break and momentum.

- Bias: H4 + H1.
- Setup: M15 liquidity raid + displacement.
- Zone: 61.8%-78.6% retracement of the raid-to-displacement impulse.
- Entry: fresh zone touch, rejection, micro BOS and momentum.
- Entry score: touch 25, rejection 25, BOS 25, momentum 25, plus setup-quality bonus.
- Difference from EMERALD: no mandatory 61.8%-70.5% sweet-spot filter and no Fib-50 reclaim requirement.
- SL: beyond raid/zone/retest wick with ATR buffer.
- TP: default RR target or opposite liquidity, whichever is farther in trade direction.

## PRIMORDIAL GOLD

**Library title:** Compression Sweep Expansion

**Description:** Detects tight M15 compression, waits for a false break/liquidity sweep outside the box and a reclaim, then enters the expansion only after M5 rejection, BOS and momentum confirmation.

- Bias: H4 + H1.
- Compression: 12 M15 bars by default; box range <= 2.20 ATR and average candle body <= 0.42 ATR.
- Bull setup: sweep below compression low then close back above it; bear setup mirrors above the high.
- Setup zone: ATR-sized band around the reclaimed compression edge.
- Entry: M5 zone touch, reclaim, wick rejection, BOS and momentum follow-through.
- Entry threshold: 70 by default; max chase 0.75 ATR.
- SL: beyond sweep extreme/zone plus ATR buffer; TP defaults to 2.5R.
## PRIMORDIAL PURPLE

**Library title:** OB + FVG MSS Sniper

**Description:** A stricter Order-Block/Fair-Value-Gap liquidity sniper. It requires sweep and stronger displacement, builds FVG/OB confluence, and uses fast-expiring M5 rejection, micro-structure break and momentum confirmation.

- Bias: H4 + H1.
- Setup: M15 sweep + displacement are mandatory; default displacement threshold is 1.20 ATR.
- Zone: FVG, OB, or hybrid FVG+OB.
- Setup expiry: 10 M5 bars by default, making it more selective/time-sensitive than BLACK.
- Entry: zone touch, rejection, micro BOS and momentum.
- Score: touch 25, rejection 25, BOS 20, momentum 15, hybrid 10 plus setup-quality bonus; threshold 76.
- Risk: 0.45% default; RR 2.5; standard partial/BE/ATR-trailing management.
- Source note: its MQ5 order comments incorrectly say “Primordial Black”; the native port will preserve PURPLE's rules but use the correct preset identity.

## PRIMORDIAL SILVER

**Library title:** Range Sweep & MSS Reversal

**Description:** Range/premium-discount reversal strategy. It builds an H1 range, looks for M15 edge sweeps and rejection followed by a displacement break, then requires an M5 retest, confirmation candle and market-structure shift before entry.

- Bias/range: H1, 24-bar range by default; midpoint/premium-discount filter enabled.
- M15 setup: sweep beyond range edge by ATR fraction, rejection candle, then strong break/displacement through the rejection candle.
- Break zone: body of the displacement/break candle.
- M5 retest: zone touch with wick rejection and close back on the correct side of zone midpoint.
- Confirmation: strong directional close beyond the zone followed by MSS beyond the retest swing.
- Chase filter: tight, 0.35 ATR base; maximum stop width 2.8 ATR.
- TP: default 2.5R; percentage-risk sizing with partial, break-even and trailing management.
## PRIMORDIAL WHITE

**Library title:** Opening Range Specialist

**Description:** First-four-hour opening-range strategy with two independent routes: liquidity sweep/reclaim and true breakout/retest. It selects the strongest valid route and waits for M5 retest, rejection, BOS, momentum and route-specific confirmation.

- Range: first 4 hours of the broker trading day, built from M15 candles; no entry until the range is complete.
- Bias: H4 + H1, while neutral bias can still allow a valid directional range setup.
- Route A: sweep outside opening-range high/low then reclaim inside.
- Route B: strong M15 breakout close beyond the range, followed by retest.
- Setup selection: evaluates bull/bear sweep and bull/bear breakout candidates and keeps the highest-scoring valid route.
- Entry: recent retest (first-retest logic enabled), rejection, M5 micro BOS, momentum and route confirmation.
- Entry threshold: 72 by default; max chase filter and ATR stop-width filter apply.
- TP: default 2.4R or the route's range-expansion target when that target is farther.

## Native strategy runtime contract

Each port should expose one pure evaluation result rather than placing an EA on a chart. The shared result should include strategy name, source version, symbol, evaluated timeframes, setup stage, direction, score/confidence, rule checklist, entry, SL, TP, risk distance, source candle time, unique signal key, and a human-readable reason.

The native runner should evaluate completed candles only where the MQ5 uses closed-bar shifts. A strategy returns WAIT until every mandatory source rule is satisfied. Order submission is delegated to the existing 8002 execution API; native strategy code must not initialize a second MetaTrader connection.

Runtime state must be workspace-scoped. A user's selected account, symbol, enabled preset, signal history and duplicate guard must never leak to another workspace. Restart recovery should restore enabled native strategies without launching EA Worker jobs.
## AI Intelligence integration contract

AI strategy selector choices will be Human Apostle plus each native preset whose source port is ready. When a preset is selected, that preset remains the rule authority. AI may scan symbols, compare valid candidates, explain setup progress and choose among valid setups, but it cannot waive a mandatory rule.

Auto Select Strategy will call the same evaluators in signal-only mode. It can compare only strategies that returned a valid setup/signal. Selection metadata should include strategy score, confirmation completeness, spread, stop distance, RR, setup age and market/timeframe compatibility. One final guarded signal is then sent through the normal 8002 order path.

## Positions controls

Open Positions will add `Close All Profitable` and `Close All Losing`. Profitable means floating P/L > 0; losing means floating P/L < 0; exactly break-even positions are excluded. The confirmation dialog must show position count and combined floating P/L before calling the existing workspace-scoped close-many backend.

## Conversion/test order

1. Build shared candle/ATR/structure helpers and the native strategy interface.
2. Port BLACK first as the common liquidity/FVG/OB base.
3. Reuse verified primitives for BLUE and PURPLE.
4. Port EMERALD and RED using shared liquidity-raid/Fibonacci primitives.
5. Port GOLD, SILVER and WHITE as their distinct compression/range/opening-range engines.
6. Add Bot Library native Start/Stop/status without EA Worker assignment for system presets.
7. Add profitable/losing bulk-close controls.
8. Add AI strategy selector, then Auto Select after individual strategy parity tests pass.
9. Add BLACK ROCK and DEAR BRUCE PREMIUM only after source/specification is available.

## Fidelity tests required

For each MQ5-backed preset, fixtures must cover BUY, SELL and WAIT/invalid paths, required-rule failure, setup expiry, chase filter, stop-width rejection, duplicate-signal guard, risk sizing, SL/TP, and restart/workspace isolation. Built-in presets must prove that no 8001 EA assignment is created and no preset EX5 is launched.
