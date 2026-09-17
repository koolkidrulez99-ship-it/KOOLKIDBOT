from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable


@dataclass(frozen=True)
class Swing:
    kind: str  # high | low
    index: int
    confirm_index: int
    time: int
    price: float
    label: str  # HH | LH | HL | LL | H | L


@dataclass
class SetupState:
    state: str = "SCANNING"
    direction: str | None = None
    trendline: dict[str, Any] | None = None
    protected_structure: float | None = None
    structural_stop: float | None = None
    shift_index: int | None = None
    shift_time: int | None = None
    retest_level: float | None = None
    retest_touched: bool = False
    last_reason: str = "Waiting for a valid bullish or bearish execution structure."


TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "H8": 28800,
    "D1": 86400,
}


def _num(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if isfinite(result) else 0.0


def normalize_candles(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            ts = int(row.get("time") or 0)
        except (TypeError, ValueError):
            continue
        o, h, l, c = (_num(row.get(k)) for k in ("open", "high", "low", "close"))
        if ts < 0 or h <= 0 or l <= 0 or h < l:
            continue
        out.append({
            "time": ts,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": int(row.get("volume") or 0),
        })
    out.sort(key=lambda row: row["time"])
    # Deduplicate by candle open timestamp while preserving the newest copy.
    deduped: dict[int, dict[str, Any]] = {row["time"]: row for row in out}
    return [deduped[key] for key in sorted(deduped)]


def completed_candles(rows: Iterable[dict[str, Any]], timeframe: str, now_ts: int | None = None) -> list[dict[str, Any]]:
    candles = normalize_candles(rows)
    if not candles:
        return []
    seconds = TIMEFRAME_SECONDS.get(timeframe.upper())
    if not seconds:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    now_value = int(now_ts or datetime.now(timezone.utc).timestamp())
    return [row for row in candles if int(row["time"]) + seconds <= now_value]


def atr(candles: list[dict[str, Any]], period: int = 14) -> float:
    if len(candles) < 2:
        return 0.0
    values: list[float] = []
    start = max(1, len(candles) - period)
    for i in range(start, len(candles)):
        cur = candles[i]
        prev = candles[i - 1]
        values.append(max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev["close"]),
            abs(cur["low"] - prev["close"]),
        ))
    return sum(values) / len(values) if values else 0.0


def detect_swings(candles: list[dict[str, Any]], left: int = 2, right: int = 2) -> list[Swing]:
    if left < 1 or right < 1:
        raise ValueError("Swing confirmation requires at least one candle on each side.")
    raw: list[tuple[str, int, float]] = []
    for i in range(left, len(candles) - right):
        high = candles[i]["high"]
        low = candles[i]["low"]
        is_high = all(high > candles[j]["high"] for j in range(i - left, i)) and all(high > candles[j]["high"] for j in range(i + 1, i + right + 1))
        is_low = all(low < candles[j]["low"] for j in range(i - left, i)) and all(low < candles[j]["low"] for j in range(i + 1, i + right + 1))
        if is_high:
            raw.append(("high", i, high))
        if is_low:
            raw.append(("low", i, low))
    raw.sort(key=lambda item: (item[1], 0 if item[0] == "low" else 1))

    last_price: dict[str, float | None] = {"high": None, "low": None}
    result: list[Swing] = []
    for kind, index, price in raw:
        prior = last_price[kind]
        if kind == "high":
            label = "H" if prior is None else ("HH" if price > prior else "LH")
        else:
            label = "L" if prior is None else ("HL" if price > prior else "LL")
        result.append(Swing(kind, index, index + right, int(candles[index]["time"]), float(price), label))
        last_price[kind] = price
    return result


def confirmed_swings(swings: list[Swing], candle_index: int) -> list[Swing]:
    return [s for s in swings if s.confirm_index <= candle_index]


def structure_at(candles: list[dict[str, Any]], swings: list[Swing], candle_index: int) -> tuple[str, str]:
    visible = confirmed_swings(swings, candle_index)
    highs = [s for s in visible if s.kind == "high"]
    lows = [s for s in visible if s.kind == "low"]
    if len(highs) < 1 or len(lows) < 1:
        return "neutral", "Not enough confirmed swings."

    close = candles[candle_index]["close"]
    # A completed close through a confirmed swing is allowed to establish structure.
    if close > highs[-1].price:
        return "bullish", f"Completed close {close:.5f} is above confirmed swing high {highs[-1].price:.5f}."
    if close < lows[-1].price:
        return "bearish", f"Completed close {close:.5f} is below confirmed swing low {lows[-1].price:.5f}."
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1].label == "HH" and lows[-1].label == "HL":
            return "bullish", "Latest confirmed swings form HH + HL."
        if highs[-1].label == "LH" and lows[-1].label == "LL":
            return "bearish", "Latest confirmed swings form LH + LL."
    return "neutral", "Confirmed swings do not yet form a clean HH/HL or LH/LL structure."


def _line_value(a: Swing, b: Swing, index: int) -> float:
    if b.index == a.index:
        return float(b.price)
    slope = (b.price - a.price) / (b.index - a.index)
    return a.price + slope * (index - a.index)


def _anchors_for_sell(swings: list[Swing], candle_index: int) -> tuple[Swing, Swing] | None:
    lows = [s for s in confirmed_swings(swings, candle_index) if s.kind == "low"]
    for i in range(len(lows) - 1, 0, -1):
        a, b = lows[i - 1], lows[i]
        if b.price > a.price and b.index < candle_index:
            return a, b
    return None


def _anchors_for_buy(swings: list[Swing], candle_index: int) -> tuple[Swing, Swing] | None:
    highs = [s for s in confirmed_swings(swings, candle_index) if s.kind == "high"]
    for i in range(len(highs) - 1, 0, -1):
        a, b = highs[i - 1], highs[i]
        if b.price < a.price and b.index < candle_index:
            return a, b
    return None


def _latest_swing(swings: list[Swing], candle_index: int, kind: str) -> Swing | None:
    rows = [s for s in confirmed_swings(swings, candle_index) if s.kind == kind]
    return rows[-1] if rows else None


def _buffer(candles: list[dict[str, Any]], upto: int, ratio: float = 0.05) -> float:
    sample = candles[: upto + 1]
    value = atr(sample, 14) * ratio
    close = abs(sample[-1]["close"]) if sample else 0
    return max(value, close * 1e-6, 1e-8)


def _bias_snapshot(candles: list[dict[str, Any]], swings: list[Swing]) -> tuple[str, str]:
    if not candles:
        return "neutral", "No completed H4 candles were available."
    return structure_at(candles, swings, len(candles) - 1)


def _serialize_swing(s: Swing | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return asdict(s)


def _confidence(state: SetupState, bias: str, rejection_ok: bool = False) -> tuple[int, list[str]]:
    score = 0
    factors: list[str] = []
    if state.direction:
        score += 20; factors.append("execution structure + direction: +20")
    if state.trendline:
        score += 20; factors.append("opposing trendline break: +20")
    if state.shift_index is not None:
        score += 20; factors.append("protected structure break: +20")
    if state.retest_touched:
        score += 15; factors.append("later retest touched: +15")
    if state.direction and bias == ("bearish" if state.direction == "sell" else "bullish"):
        score += 15; factors.append("H4 bias aligned: +15")
    if rejection_ok:
        score += 10; factors.append("rejection candle confirmed: +10")
    return min(100, score), factors


def run_human_apostle_trial(
    execution_rows: Iterable[dict[str, Any]],
    bias_rows: Iterable[dict[str, Any]],
    *,
    symbol: str,
    account_login: int,
    now_ts: int | None = None,
    swing_left: int = 2,
    swing_right: int = 2,
) -> dict[str, Any]:
    """Signal-only Human Apostle trial.

    This intentionally performs no order execution. It replays only completed M15
    candles, uses confirmed fractal swings, waits for trendline break -> protected
    structure break -> later retest -> rejection, and requires H4 alignment before
    it publishes BUY/SELL on the latest completed candle.
    """
    exec_tf = "M15"
    bias_tf = "H4"
    execution = completed_candles(execution_rows, exec_tf, now_ts)
    bias = completed_candles(bias_rows, bias_tf, now_ts)
    if len(execution) < 25:
        raise ValueError(f"Human Apostle trial needs at least 25 completed {exec_tf} candles; received {len(execution)}.")
    if len(bias) < 8:
        raise ValueError(f"Human Apostle trial needs at least 8 completed {bias_tf} candles; received {len(bias)}.")

    exec_swings = detect_swings(execution, swing_left, swing_right)
    bias_swings = detect_swings(bias, swing_left, swing_right)
    bias_structure, bias_reason = _bias_snapshot(bias, bias_swings)

    state = SetupState()
    previous_structure = "neutral"
    current_structure = "neutral"
    structure_reason = ""
    last_signal: dict[str, Any] | None = None
    latest_touch_without_confirmation = False
    latest_index = len(execution) - 1
    signal_on_latest = False

    # Start only once there is enough room for confirmed fractals.
    for i in range(max(6, swing_left + swing_right + 2), len(execution)):
        candle = execution[i]
        current_structure, structure_reason = structure_at(execution, exec_swings, i)
        buf = _buffer(execution, i)
        tolerance = max(buf * 2.0, atr(execution[: i + 1], 14) * 0.08)

        if state.state == "SIGNAL_RESET":
            state = SetupState()

        if state.state == "SCANNING":
            if current_structure == "bullish":
                anchors = _anchors_for_sell(exec_swings, i)
                if anchors:
                    a, b = anchors
                    line = _line_value(a, b, i)
                    if candle["close"] < line - buf:
                        protected = b
                        stop_ref = _latest_swing(exec_swings, i, "high")
                        state = SetupState(
                            state="WAITING_STRUCTURE_SHIFT",
                            direction="sell",
                            trendline={"anchor_1": _serialize_swing(a), "anchor_2": _serialize_swing(b), "break_index": i, "break_time": candle["time"], "line_at_break": line, "close": candle["close"]},
                            protected_structure=protected.price,
                            structural_stop=stop_ref.price if stop_ref else None,
                            last_reason="Ascending HL trendline broke on a completed close; waiting for protected HL to break.",
                        )
            elif current_structure == "bearish":
                anchors = _anchors_for_buy(exec_swings, i)
                if anchors:
                    a, b = anchors
                    line = _line_value(a, b, i)
                    if candle["close"] > line + buf:
                        protected = b
                        stop_ref = _latest_swing(exec_swings, i, "low")
                        state = SetupState(
                            state="WAITING_STRUCTURE_SHIFT",
                            direction="buy",
                            trendline={"anchor_1": _serialize_swing(a), "anchor_2": _serialize_swing(b), "break_index": i, "break_time": candle["time"], "line_at_break": line, "close": candle["close"]},
                            protected_structure=protected.price,
                            structural_stop=stop_ref.price if stop_ref else None,
                            last_reason="Descending LH trendline broke on a completed close; waiting for protected LH to break.",
                        )

        elif state.state == "WAITING_STRUCTURE_SHIFT":
            if state.direction == "sell":
                if state.structural_stop is not None and candle["close"] > state.structural_stop + buf:
                    state = SetupState(last_reason="Sell candidate invalidated by a completed close above the stored structural stop reference.")
                elif state.protected_structure is not None and candle["close"] < state.protected_structure - buf:
                    state.state = "WAITING_RETEST"
                    state.shift_index = i
                    state.shift_time = candle["time"]
                    state.retest_level = state.protected_structure
                    state.last_reason = "Protected HL broke on a completed close; waiting for a later retest."
            elif state.direction == "buy":
                if state.structural_stop is not None and candle["close"] < state.structural_stop - buf:
                    state = SetupState(last_reason="Buy candidate invalidated by a completed close below the stored structural stop reference.")
                elif state.protected_structure is not None and candle["close"] > state.protected_structure + buf:
                    state.state = "WAITING_RETEST"
                    state.shift_index = i
                    state.shift_time = candle["time"]
                    state.retest_level = state.protected_structure
                    state.last_reason = "Protected LH broke on a completed close; waiting for a later retest."

        elif state.state == "WAITING_RETEST":
            # A structure-shift candle is explicitly forbidden from acting as its own retest.
            if state.shift_index is not None and i <= state.shift_index:
                continue
            level = float(state.retest_level or 0)
            if state.direction == "sell":
                invalid = state.structural_stop is not None and candle["close"] > state.structural_stop + buf
                if invalid:
                    state = SetupState(last_reason="Sell retest candidate invalidated above the structural stop reference.")
                    continue
                touched = candle["high"] >= level - tolerance and candle["low"] <= level + tolerance
                if touched:
                    state.retest_touched = True
                    rejection = candle["close"] < level and candle["close"] < candle["open"]
                    latest_touch_without_confirmation = i == latest_index and not rejection
                    if rejection:
                        entry = candle["close"]
                        stop_base = state.structural_stop if state.structural_stop is not None else candle["high"]
                        sl = max(stop_base, candle["high"]) + buf
                        risk = sl - entry
                        aligned = bias_structure == "bearish"
                        if risk > 0 and aligned:
                            tp = entry - (2.0 * risk)
                            conf, factors = _confidence(state, bias_structure, True)
                            last_signal = {
                                "direction": "SELL", "index": i, "time": candle["time"], "entry": entry,
                                "sl": sl, "tp": tp, "risk_distance": risk, "r_multiple": 2.0,
                                "confidence": conf, "confidence_factors": factors,
                                "reason": "All Human Apostle trial stages completed and H4 bias is bearish.",
                            }
                            signal_on_latest = i == latest_index
                        elif not aligned:
                            state.last_reason = f"Retest rejected correctly, but H4 bias is {bias_structure}; SELL is blocked."
                            continue
                        state.state = "SIGNAL_RESET"
            elif state.direction == "buy":
                invalid = state.structural_stop is not None and candle["close"] < state.structural_stop - buf
                if invalid:
                    state = SetupState(last_reason="Buy retest candidate invalidated below the structural stop reference.")
                    continue
                touched = candle["low"] <= level + tolerance and candle["high"] >= level - tolerance
                if touched:
                    state.retest_touched = True
                    rejection = candle["close"] > level and candle["close"] > candle["open"]
                    latest_touch_without_confirmation = i == latest_index and not rejection
                    if rejection:
                        entry = candle["close"]
                        stop_base = state.structural_stop if state.structural_stop is not None else candle["low"]
                        sl = min(stop_base, candle["low"]) - buf
                        risk = entry - sl
                        aligned = bias_structure == "bullish"
                        if risk > 0 and aligned:
                            tp = entry + (2.0 * risk)
                            conf, factors = _confidence(state, bias_structure, True)
                            last_signal = {
                                "direction": "BUY", "index": i, "time": candle["time"], "entry": entry,
                                "sl": sl, "tp": tp, "risk_distance": risk, "r_multiple": 2.0,
                                "confidence": conf, "confidence_factors": factors,
                                "reason": "All Human Apostle trial stages completed and H4 bias is bullish.",
                            }
                            signal_on_latest = i == latest_index
                        elif not aligned:
                            state.last_reason = f"Retest rejected correctly, but H4 bias is {bias_structure}; BUY is blocked."
                            continue
                        state.state = "SIGNAL_RESET"

        previous_structure = current_structure

    # Re-evaluate structure on the latest completed candle for the monitor output.
    current_structure, structure_reason = structure_at(execution, exec_swings, latest_index)
    structure_before_latest = structure_at(execution, exec_swings, latest_index - 1)[0] if latest_index > 0 else "neutral"
    if signal_on_latest and last_signal:
        decision = last_signal["direction"]
        state_label = "POSITION_SIGNAL"
        reason = last_signal["reason"]
        confidence = int(last_signal["confidence"])
        confidence_factors = list(last_signal["confidence_factors"])
    else:
        state_label = state.state if state.state != "SIGNAL_RESET" else "SCANNING"
        if latest_touch_without_confirmation:
            decision = "WAIT FOR CANDLE CONFIRMATION"
        elif state_label == "WAITING_STRUCTURE_SHIFT":
            decision = "WAIT FOR STRUCTURE SHIFT"
        elif state_label == "WAITING_RETEST":
            decision = "WAIT FOR LATER RETEST"
        elif current_structure in {"bullish", "bearish"}:
            decision = "WAIT FOR TRENDLINE BREAK"
        else:
            decision = "SCANNING"
        reason = state.last_reason
        confidence, confidence_factors = _confidence(state, bias_structure, False)

    visible = confirmed_swings(exec_swings, latest_index)
    last_high = next((s for s in reversed(visible) if s.kind == "high"), None)
    last_low = next((s for s in reversed(visible) if s.kind == "low"), None)
    latest = execution[-1]
    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "trial_version": "0.1-session-1",
        "strategy": "Human Apostle Trial",
        "mode": "SIGNAL_ONLY",
        "execution": "SIGNAL ONLY — ORDER NOT EXECUTED.",
        "account_login": int(account_login),
        "symbol": symbol,
        "execution_timeframe": exec_tf,
        "bias_timeframe": bias_tf,
        "generated_at": generated_at,
        "latest_completed_candle": latest,
        "completed_candles": {"execution": len(execution), "bias": len(bias)},
        "state": state_label,
        "decision": decision,
        "reason": reason,
        "execution_structure": current_structure,
        "execution_structure_reason": structure_reason,
        "bias_structure": bias_structure,
        "bias_reason": bias_reason,
        "previous_structure": structure_before_latest,
        "last_confirmed_high": _serialize_swing(last_high),
        "last_confirmed_low": _serialize_swing(last_low),
        "trendline": state.trendline,
        "protected_structure": state.protected_structure,
        "structure_shift": {
            "confirmed": state.shift_index is not None,
            "index": state.shift_index,
            "time": state.shift_time,
        },
        "retest": {
            "level": state.retest_level,
            "touched": state.retest_touched,
            "same_candle_blocked": True,
        },
        "confidence": confidence,
        "confidence_factors": confidence_factors,
        "proposed_trade": last_signal if signal_on_latest else None,
        "last_historical_signal": last_signal,
        "rules": {
            "completed_candles_only": True,
            "swing_left": swing_left,
            "swing_right": swing_right,
            "same_candle_shift_retest": False,
            "required_sequence": ["structure", "opposing trendline break", "protected structure break", "later retest", "rejection candle", "H4 alignment"],
            "take_profit_r": 2.0,
        },
    }
