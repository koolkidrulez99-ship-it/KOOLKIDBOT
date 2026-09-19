"""Deterministic Human Apostle / Dear Bruce market-structure intelligence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
from decimal import Decimal, ROUND_FLOOR
from typing import Iterable


TIMEFRAMES = {"M1", "M5", "M15", "M30", "H1", "H4", "H8", "D1"}
DEAR_BRUCE_BIAS = {"M1": ("M5", "M15"), "M5": ("M15", "H1"), "M15": ("H1", "H4")}
DECISIONS = {
    "SCANNING", "WAIT FOR TRENDLINE BREAK", "WAIT FOR STRUCTURE SHIFT",
    "WAIT FOR LATER RETEST", "WAIT FOR CANDLE CONFIRMATION", "BUY", "SELL",
    "MANAGE POSITION", "REJECT SETUP",
}


@dataclass(frozen=True)
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    complete: bool = True


@dataclass(frozen=True)
class Swing:
    index: int
    time: int
    price: float
    kind: str
    label: str = ""


@dataclass
class SetupState:
    account: str
    symbol: str
    timeframe: str
    strategy: str = "HUMAN APOSTLE"
    state: str = "SCANNING"
    direction: str = ""
    structure: str = "NEUTRAL"
    protected_structure: float | None = None
    stop_reference: float | None = None
    retest_level: float | None = None
    trendline: tuple[tuple[int, float], tuple[int, float]] | None = None
    break_index: int | None = None
    shift_index: int | None = None
    break_time: int | None = None
    shift_time: int | None = None
    last_processed_time: int = 0
    reason: str = ""
    score: int = 0
    features: dict = field(default_factory=dict)

    def reset(self, reason=""):
        account, symbol, timeframe, strategy = self.account, self.symbol, self.timeframe, self.strategy
        self.__dict__.update(SetupState(account, symbol, timeframe, strategy).__dict__)
        self.reason = reason


@dataclass(frozen=True)
class RiskSpec:
    equity: float
    risk_percent: float = 1.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01


def completed(rows: Iterable[dict | Candle]) -> list[Candle]:
    output = []
    for row in rows:
        candle = row if isinstance(row, Candle) else Candle(
            int(row["time"]), float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]), float(row.get("volume", 0)),
            bool(row.get("complete", True)),
        )
        if not all(math.isfinite(v) for v in (candle.open, candle.high, candle.low, candle.close)) or not (
            candle.low <= min(candle.open, candle.close) <= max(candle.open, candle.close) <= candle.high
        ):
            raise ValueError("Invalid OHLC candle data.")
        if candle.complete:
            output.append(candle)
    return sorted({c.time: c for c in output}.values(), key=lambda c: c.time)


def confirmed_swings(candles: list[Candle], radius=2) -> tuple[list[Swing], list[Swing]]:
    highs, lows = [], []
    for i in range(radius, len(candles) - radius):
        window = candles[i - radius:i + radius + 1]
        if candles[i].high == max(c.high for c in window) and sum(c.high == candles[i].high for c in window) == 1:
            highs.append(Swing(i, candles[i].time, candles[i].high, "HIGH"))
        if candles[i].low == min(c.low for c in window) and sum(c.low == candles[i].low for c in window) == 1:
            lows.append(Swing(i, candles[i].time, candles[i].low, "LOW"))
    highs = [Swing(x.index, x.time, x.price, x.kind, "HH" if i and x.price > highs[i-1].price else "LH" if i else "H") for i, x in enumerate(highs)]
    lows = [Swing(x.index, x.time, x.price, x.kind, "HL" if i and x.price > lows[i-1].price else "LL" if i else "L") for i, x in enumerate(lows)]
    return highs, lows


def market_structure(candles: list[Candle], highs: list[Swing], lows: list[Swing]) -> str:
    if not candles:
        return "NEUTRAL"
    close = candles[-1].close
    if highs and close > highs[-1].price:
        return "BULLISH"
    if lows and close < lows[-1].price:
        return "BEARISH"
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
            return "BULLISH"
        if highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
            return "BEARISH"
    return "NEUTRAL"


def trendline_value(first: Swing, second: Swing, index: int) -> float:
    if second.index == first.index:
        raise ValueError("Trendline anchors must use different candles.")
    slope = (second.price - first.price) / (second.index - first.index)
    return first.price + slope * (index - first.index)


def rejection(candle: Candle, direction: str, level: float, tolerance: float, require_color=True) -> bool:
    touched = candle.low <= level + tolerance and candle.high >= level - tolerance
    if direction == "BUY":
        return touched and candle.close > level and (not require_color or candle.close > candle.open)
    return touched and candle.close < level and (not require_color or candle.close < candle.open)


def position_size(entry: float, stop: float, spec: RiskSpec) -> float:
    values = (entry, stop, spec.equity, spec.risk_percent, spec.tick_size, spec.tick_value,
              spec.volume_min, spec.volume_max, spec.volume_step)
    if not all(math.isfinite(float(v)) for v in values) or min(spec.equity, spec.risk_percent, spec.tick_size, spec.tick_value, spec.volume_min, spec.volume_step) <= 0 or spec.volume_max < spec.volume_min or spec.risk_percent > 100:
        raise ValueError("Complete MT5 equity, tick-value and volume information is required.")
    distance = abs(entry - stop)
    if distance <= 0:
        raise ValueError("Structural stop distance must be positive.")
    dec = lambda value: Decimal(str(value))
    raw = (dec(spec.equity) * dec(spec.risk_percent) / 100) / ((abs(dec(entry) - dec(stop)) / dec(spec.tick_size)) * dec(spec.tick_value))
    step = Decimal(str(spec.volume_step))
    volume = (min(raw, dec(spec.volume_max)) / step).to_integral_value(rounding=ROUND_FLOOR) * step
    if volume < dec(spec.volume_min):
        raise ValueError("Safe calculated volume is below the broker minimum.")
    return float(volume)


class ApostleEngine:
    def __init__(self, buffer=0.0, retest_tolerance=0.0, confirmation=True, target_r=2.0, stale_bars=80, threshold=0):
        if not all(math.isfinite(float(v)) for v in (buffer, retest_tolerance, target_r, threshold)) or not 0 <= float(threshold) <= 100:
            raise ValueError("AI settings must be finite; confidence must be between 0 and 100.")
        self.buffer = max(0.0, float(buffer))
        self.tolerance = max(0.0, float(retest_tolerance))
        self.confirmation = bool(confirmation)
        self.target_r = max(0.1, float(target_r))
        self.stale_bars = max(5, int(stale_bars))
        self.threshold = float(threshold)

    def evaluate(self, state: SetupState, rows, bias=None, risk: RiskSpec | None = None):
        candles = completed(rows)
        if len(candles) < 7:
            return self._decision(state, "SCANNING", "Not enough completed candles.")
        highs, lows = confirmed_swings(candles)
        structure = market_structure(candles, highs, lows)
        state.structure = structure
        i, candle = len(candles) - 1, candles[-1]
        if candle.time <= state.last_processed_time:
            return self._decision(state, self._state_decision(state), "No new completed candle.")
        state.last_processed_time = candle.time
        # Persist timestamps: an MT5 history window slides while its last index stays constant.
        for name in ("break", "shift"):
            index = getattr(state, name + "_index")
            if getattr(state, name + "_time") is None and index is not None and 0 <= index < len(candles):
                setattr(state, name + "_time", candles[index].time)
        if state.state in ("SIGNAL_READY", "POSITION_ACTIVE"):
            state.reset("Previous signal recorded; scanning the next completed candle.")
            state.last_processed_time = candle.time
            state.structure = structure
        if state.break_time is not None and (state.break_time < candles[0].time or sum(c.time > state.break_time for c in candles) > self.stale_bars):
            state.reset("Setup expired before confirmation.")
            state.last_processed_time = candle.time

        if state.state == "SCANNING":
            prior_highs, prior_lows = confirmed_swings(candles[:-1])
            origin_structure = market_structure(candles[:-1], prior_highs, prior_lows)
            if origin_structure == "NEUTRAL":
                origin_structure = structure
            if origin_structure == "BULLISH" and len(lows) >= 2 and lows[-1].price > lows[-2].price:
                a, b = lows[-2], lows[-1]
                state.trendline = ((a.index, a.price), (b.index, b.price))
                state.reason = "Bullish structure tracked; waiting for close below rising-HL trendline."
                if candle.close < trendline_value(a, b, i) - self.buffer:
                    state.state = "WAITING_FOR_STRUCTURE_SHIFT"
                    state.direction = "SELL"
                    state.protected_structure = b.price
                    state.stop_reference = max((h.price for h in highs if h.index > b.index), default=max(c.high for c in candles[b.index:]))
                    state.break_index = i
                    state.break_time = candle.time
                    return self._decision(state, "WAIT FOR STRUCTURE SHIFT", "Opposing trendline broke on a completed close.")
                return self._decision(state, "WAIT FOR TRENDLINE BREAK", state.reason)
            if origin_structure == "BEARISH" and len(highs) >= 2 and highs[-1].price < highs[-2].price:
                a, b = highs[-2], highs[-1]
                state.trendline = ((a.index, a.price), (b.index, b.price))
                state.reason = "Bearish structure tracked; waiting for close above falling-LH trendline."
                if candle.close > trendline_value(a, b, i) + self.buffer:
                    state.state = "WAITING_FOR_STRUCTURE_SHIFT"
                    state.direction = "BUY"
                    state.protected_structure = b.price
                    state.stop_reference = min((x.price for x in lows if x.index > b.index), default=min(c.low for c in candles[b.index:]))
                    state.break_index = i
                    state.break_time = candle.time
                    return self._decision(state, "WAIT FOR STRUCTURE SHIFT", "Opposing trendline broke on a completed close.")
                return self._decision(state, "WAIT FOR TRENDLINE BREAK", state.reason)
            return self._decision(state, "SCANNING", "Structure is neutral or lacks two confirmed trendline anchors.")

        if state.direction and state.stop_reference is not None and (
            (state.direction == "BUY" and candle.close < state.stop_reference - self.buffer) or
            (state.direction == "SELL" and candle.close > state.stop_reference + self.buffer)
        ):
            state.reset("Setup invalidated beyond its structural stop.")
            state.last_processed_time = candle.time
            return self._decision(state, "REJECT SETUP", state.reason)

        if state.state == "WAITING_FOR_STRUCTURE_SHIFT":
            shifted = (state.direction == "SELL" and candle.close < state.protected_structure - self.buffer) or (state.direction == "BUY" and candle.close > state.protected_structure + self.buffer)
            if not shifted:
                return self._decision(state, "WAIT FOR STRUCTURE SHIFT", "Protected structure has not broken on a completed close.")
            state.state = "WAITING_FOR_RETEST"
            state.retest_level = state.protected_structure
            state.shift_index = i
            state.shift_time = candle.time
            return self._decision(state, "WAIT FOR LATER RETEST", "Structure shifted; the same candle cannot confirm its own retest.")

        if state.state == "WAITING_FOR_RETEST":
            if state.shift_time is None or candle.time <= state.shift_time:
                return self._decision(state, "WAIT FOR LATER RETEST", "Waiting for a candle after the structure-shift candle.")
            level = float(state.retest_level)
            touched = candle.low <= level + self.tolerance if state.direction == "BUY" else candle.high >= level - self.tolerance
            if not touched:
                return self._decision(state, "WAIT FOR LATER RETEST", "Price has not retested protected structure.")
            if not rejection(candle, state.direction, level, self.tolerance, self.confirmation):
                return self._decision(state, "WAIT FOR CANDLE CONFIRMATION", "Retest occurred without a valid completed rejection candle.")
            required_bias = [str(x).upper() for x in (bias or [])]
            wanted = "BULLISH" if state.direction == "BUY" else "BEARISH"
            if structure != wanted:
                state.reset("Execution structure no longer agrees with the setup.")
                state.last_processed_time = candle.time
                return self._decision(state, "REJECT SETUP", state.reason)
            if required_bias and any(x != wanted for x in required_bias):
                state.reset("Required higher-timeframe alignment failed.")
                state.last_processed_time = candle.time
                return self._decision(state, "REJECT SETUP", "Required higher-timeframe alignment failed.")
            entry = candle.close
            reference = state.stop_reference
            if reference is None:
                reference = candle.low if state.direction == "BUY" else candle.high
            stop = (float(reference) - self.buffer) if state.direction == "BUY" else (float(reference) + self.buffer)
            if (state.direction == "BUY" and stop >= entry) or (state.direction == "SELL" and stop <= entry):
                fallback = candle.low - self.buffer if state.direction == "BUY" else candle.high + self.buffer
                stop = fallback
            if stop == entry:
                state.reset("A structural stop could not be calculated.")
                return self._decision(state, "REJECT SETUP", state.reason)
            target = entry + self.target_r * abs(entry - stop) * (1 if state.direction == "BUY" else -1)
            factors = {"execution_structure": 25, "completed_structure_shift": 20,
                       "later_retest": 20, "rejection_candle": 20,
                       "higher_timeframe_alignment": 15 if required_bias else 0}
            score = sum(factors.values())
            if score < self.threshold:
                state.reset("Confirmed setup is below the configured confidence threshold.")
                state.last_processed_time = candle.time
                return self._decision(state, "REJECT SETUP", state.reason, score=score, confidence_factors=factors)
            volume = None
            risk_error = None
            if risk:
                try:
                    volume = position_size(entry, stop, risk)
                except ValueError as exc:
                    risk_error = str(exc)
            if risk_error:
                state.reset(risk_error)
                return self._decision(state, "REJECT SETUP", risk_error, score=score)
            state.state = "SIGNAL_READY"
            state.score = score
            state.features = {"entry": entry, "sl": stop, "tp": target, "r": self.target_r, "volume": volume,
                              "risk_validated": risk is not None, "confidence_factors": factors}
            return self._decision(state, state.direction, "All mandatory Apostle stages passed.", score=score, **state.features)

        return self._decision(state, "SCANNING", "No executed position is managed by this signal-only engine.")

    @staticmethod
    def _state_decision(state):
        return {"WAITING_FOR_STRUCTURE_SHIFT": "WAIT FOR STRUCTURE SHIFT", "WAITING_FOR_RETEST": "WAIT FOR LATER RETEST"}.get(state.state, "SCANNING")

    @staticmethod
    def _decision(state, decision, reason, score=0, **extra):
        assert decision in DECISIONS
        return {"decision": decision, "reason": reason, "score": int(score), "state": asdict(state), **extra}


def approve_ex5_signal(signal: dict, analysis: dict, threshold=75) -> dict:
    required = {"ea", "magic", "symbol", "direction", "entry", "sl", "tp", "timeframe"}
    if not required.issubset(signal):
        return {"decision": "REJECT", "reason": "EX5 signal metadata is incomplete.", "score": 0}
    if analysis.get("decision") not in ("BUY", "SELL"):
        return {"decision": "DELAY", "reason": analysis.get("reason", "Strategy stages are incomplete."), "score": analysis.get("score", 0)}
    if signal["direction"].upper() != analysis["decision"]:
        return {"decision": "REJECT", "reason": "EX5 direction conflicts with the completed Apostle setup.", "score": analysis.get("score", 0)}
    score = min(100, int(analysis.get("score", 0)) + 20)
    return {"decision": "APPROVE" if score >= threshold else "DELAY", "reason": "EX5 signal and Apostle analysis agree." if score >= threshold else "Confidence is below threshold.", "score": score}


def backtest(rows, *, account="BACKTEST", symbol="UNKNOWN", timeframe="M15", strategy="HUMAN APOSTLE", bias=None, engine=None):
    candles = completed(rows)
    engine = engine or ApostleEngine()
    state = SetupState(account, symbol, timeframe, strategy)
    trades, rejected = [], 0
    occupied_until = -1
    for end in range(7, len(candles)):
        if end <= occupied_until:
            continue
        result = engine.evaluate(state, candles[:end + 1], bias=bias)
        if result["decision"] == "REJECT SETUP":
            rejected += 1
        if result["decision"] not in ("BUY", "SELL"):
            continue
        entry, stop, target = result["entry"], result["sl"], result["tp"]
        direction = result["decision"]
        outcome, r_value, mfe, mae = "OPEN", 0.0, 0.0, 0.0
        risk_distance = abs(entry - stop)
        exit_index = len(candles) - 1
        for future_index, future in enumerate(candles[end + 1:], end + 1):
            favorable = (future.high - entry) if direction == "BUY" else (entry - future.low)
            adverse = (entry - future.low) if direction == "BUY" else (future.high - entry)
            mfe, mae = max(mfe, favorable / risk_distance), max(mae, adverse / risk_distance)
            stop_hit = future.low <= stop if direction == "BUY" else future.high >= stop
            target_hit = future.high >= target if direction == "BUY" else future.low <= target
            if stop_hit or target_hit:
                # If both occur in one candle, use the conservative stop-first result.
                outcome, r_value = ("LOSS", -1.0) if stop_hit else ("WIN", engine.target_r)
                exit_index = future_index
                break
        trades.append({"time": candles[end].time, "direction": direction, "entry": entry, "sl": stop, "tp": target, "outcome": outcome, "r": r_value, "mfe": round(mfe, 4), "mae": round(mae, 4)})
        state.reset("Backtest position resolved.")
        occupied_until = exit_index
        trades[-1]["exit_time"] = candles[exit_index].time if outcome != "OPEN" else None
        state.last_processed_time = candles[exit_index].time
    closed = [trade for trade in trades if trade["outcome"] != "OPEN"]
    wins = sum(trade["outcome"] == "WIN" for trade in closed)
    losses = sum(trade["outcome"] == "LOSS" for trade in closed)
    gross_win = sum(max(0, trade["r"]) for trade in closed)
    gross_loss = abs(sum(min(0, trade["r"]) for trade in closed))
    equity, peak, drawdown = 0.0, 0.0, 0.0
    for trade in closed:
        equity += trade["r"]
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "total_trades": len(closed), "wins": wins, "losses": losses,
        "win_rate": round(100 * wins / len(closed), 2) if closed else 0,
        "net_r": round(sum(trade["r"] for trade in closed), 4),
        "r_expectancy": round(sum(trade["r"] for trade in closed) / len(closed), 4) if closed else 0,
        "max_drawdown_r": round(drawdown, 4),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else (None if not gross_win else "infinite"),
        "average_win_r": round(gross_win / wins, 4) if wins else 0,
        "average_loss_r": round(gross_loss / losses, 4) if losses else 0,
        "rejected_setups": rejected, "open_unresolved": len(trades) - len(closed), "trades": trades,
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()
