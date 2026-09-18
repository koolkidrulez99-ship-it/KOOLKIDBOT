from __future__ import annotations

from typing import Any

from ai_trial.engine import (
    SetupState,
    _anchors_for_buy,
    _anchors_for_sell,
    _latest_swing,
    _line_value,
    confirmed_swings,
    detect_swings,
    structure_at,
)

from .catalog import NATIVE_PRESETS
from .common import Series
from .models import NativeSignal

_TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400}


def _meta(key: str) -> dict[str, Any]:
    return next(value for value in NATIVE_PRESETS.values() if value["key"] == key)


def _signal(key: str, **updates: Any) -> NativeSignal:
    meta = _meta(key)
    row = NativeSignal(strategy_key=key, strategy_name=meta["name"], title=meta["title"])
    for name, value in updates.items():
        setattr(row, name, value)
    return row


def _series(data: dict[str, Any], tf: str) -> Series:
    value = data.get(tf)
    if not isinstance(value, Series):
        raise ValueError(f"{tf} candle series is required")
    return value


def _point(data: dict[str, Any]) -> float:
    info = dict(data.get("symbol_info") or {})
    quote = dict(data.get("quote") or {})
    return max(float(info.get("point") or quote.get("point") or 0), 1e-10)


def _spread_points(data: dict[str, Any]) -> float:
    return float((data.get("quote") or {}).get("spread_points") or 0)


def _quote_price(data: dict[str, Any], direction: str, fallback: float) -> float:
    quote = dict(data.get("quote") or {})
    value = float(quote.get("ask") or 0) if direction == "BUY" else float(quote.get("bid") or 0)
    return value if value > 0 else fallback


def _bias_at(rows: list[dict[str, Any]], swings: list[Any], eval_epoch: int, timeframe: str) -> tuple[str, str]:
    seconds = int(_TF_SECONDS[timeframe])
    index = -1
    for i, row in enumerate(rows):
        if int(row["time"]) + seconds <= int(eval_epoch):
            index = i
        else:
            break
    if index < 0:
        return "neutral", f"No completed {timeframe} bias candle is available yet."
    return structure_at(rows, swings, index)


def _stage_score(state: SetupState, bias: str, rejection: bool = False) -> float:
    score = 0.0
    if state.direction:
        score += 20
    if state.trendline:
        score += 25
    if state.shift_index is not None:
        score += 25
    if state.retest_touched:
        score += 15
    expected = "bullish" if state.direction == "buy" else "bearish"
    if state.direction and bias == expected:
        score += 10
    if rejection:
        score += 5
    return min(100.0, score)


def _rules(key: str, exec_tf: str, bias_tf: str, require_bias_alignment: bool) -> dict[str, Any]:
    return {
        "source": _meta(key).get("source"),
        "source_sha256": _meta(key).get("source_sha256"),
        "native": True,
        "completed_candles_only": True,
        "ea_worker_used": False,
        "execution_timeframe": exec_tf,
        "bias_timeframe": bias_tf,
        "sequence": [
            "existing structure",
            "opposing trendline break",
            "protected structure break",
            "market-structure shift",
            "later retest",
            "rejection candle",
            "entry",
        ],
        "higher_bias_alignment_required": require_bias_alignment,
        "same_candle_shift_retest": False,
    }


def _evaluate_reversal(
    data: dict[str, Any],
    *,
    key: str,
    exec_tf: str,
    bias_tf: str,
    lookback: int,
    swing_strength: int,
    level_tolerance_points: int,
    trendline_buffer_points: int,
    stop_buffer_points: int,
    target_rr: float,
    risk_percent: float,
    require_bias_alignment: bool,
    require_directional_rejection: bool,
    reset_on_exec_misalignment: bool,
    max_spread_points: float | None,
    management: dict[str, Any] | None = None,
) -> NativeSignal:
    execution = list(_series(data, exec_tf).rows)[-max(lookback, 40):]
    bias_rows = list(_series(data, bias_tf).rows)[-max(lookback, 40):]
    rules = _rules(key, exec_tf, bias_tf, require_bias_alignment)
    if len(execution) < max(25, swing_strength * 2 + 8) or len(bias_rows) < 8:
        return _signal(key, stage="WAITING_DATA", reason="Completed candle history is still loading.", rules=rules)

    point = _point(data)
    if max_spread_points is not None and _spread_points(data) > float(max_spread_points):
        rules["spread_ok"] = False
        return _signal(
            key,
            stage="BLOCKED_SPREAD",
            reason=f"Spread is above the source limit of {max_spread_points:.0f} points.",
            rules=rules,
        )
    rules["spread_ok"] = True

    exec_swings = detect_swings(execution, swing_strength, swing_strength)
    bias_swings = detect_swings(bias_rows, swing_strength, swing_strength)
    state = SetupState()
    previous_structure = "neutral"
    latest_index = len(execution) - 1
    latest_structure = "neutral"
    latest_structure_reason = ""
    latest_bias = "neutral"
    latest_bias_reason = ""
    last_reason = "Waiting for a valid execution structure."

    for i in range(max(6, swing_strength * 2 + 2), len(execution)):
        candle = execution[i]
        current_structure, structure_reason = structure_at(execution, exec_swings, i)
        eval_epoch = int(candle["time"]) + int(_TF_SECONDS[exec_tf])
        bias_structure, bias_reason = _bias_at(bias_rows, bias_swings, eval_epoch, bias_tf)
        latest_structure, latest_structure_reason = current_structure, structure_reason
        latest_bias, latest_bias_reason = bias_structure, bias_reason

        if state.state == "SIGNAL_RESET":
            state = SetupState()

        if state.state == "SCANNING":
            prior = previous_structure
            if prior == "bullish":
                anchors = _anchors_for_sell(exec_swings, i)
                if anchors:
                    a, b = anchors
                    line = _line_value(a, b, i)
                    if float(candle["close"]) < line - trendline_buffer_points * point:
                        visible = confirmed_swings(exec_swings, i)
                        lows = [s for s in visible if s.kind == "low"]
                        highs = [s for s in visible if s.kind == "high"]
                        if lows and len(highs) >= 2:
                            state = SetupState(
                                state="WAITING_STRUCTURE_SHIFT",
                                direction="sell",
                                trendline={"break_time": candle["time"], "line_at_break": line},
                                protected_structure=float(lows[-1].price),
                                structural_stop=max(float(highs[-2].price), float(highs[-1].price)),
                                last_reason="Bullish HL trendline broke; waiting for the protected HL to break.",
                            )
            elif prior == "bearish":
                anchors = _anchors_for_buy(exec_swings, i)
                if anchors:
                    a, b = anchors
                    line = _line_value(a, b, i)
                    if float(candle["close"]) > line + trendline_buffer_points * point:
                        visible = confirmed_swings(exec_swings, i)
                        highs = [s for s in visible if s.kind == "high"]
                        lows = [s for s in visible if s.kind == "low"]
                        if highs and len(lows) >= 2:
                            state = SetupState(
                                state="WAITING_STRUCTURE_SHIFT",
                                direction="buy",
                                trendline={"break_time": candle["time"], "line_at_break": line},
                                protected_structure=float(highs[-1].price),
                                structural_stop=min(float(lows[-2].price), float(lows[-1].price)),
                                last_reason="Bearish LH trendline broke; waiting for the protected LH to break.",
                            )

        elif state.state == "WAITING_STRUCTURE_SHIFT":
            shifted = (
                state.direction == "sell"
                and state.protected_structure is not None
                and float(candle["close"]) < float(state.protected_structure)
            ) or (
                state.direction == "buy"
                and state.protected_structure is not None
                and float(candle["close"]) > float(state.protected_structure)
            )
            if shifted:
                expected_bias = "bearish" if state.direction == "sell" else "bullish"
                if require_bias_alignment and bias_structure != expected_bias:
                    last_reason = f"Protected structure broke, but {bias_tf} bias is {bias_structure}; setup reset."
                    state = SetupState(last_reason=last_reason)
                else:
                    state.state = "WAITING_RETEST"
                    state.shift_index = i
                    state.shift_time = int(candle["time"])
                    state.retest_level = float(state.protected_structure or 0)
                    state.last_reason = "Protected structure broke; market-structure shift confirmed. Waiting for a later retest."

        elif state.state == "WAITING_RETEST":
            expected_exec = "bearish" if state.direction == "sell" else "bullish"
            expected_bias = expected_exec
            if current_structure != expected_exec:
                if reset_on_exec_misalignment:
                    state = SetupState(last_reason=f"{exec_tf} structure no longer agrees with the setup; setup reset.")
                previous_structure = current_structure
                continue
            if require_bias_alignment and bias_structure != expected_bias:
                previous_structure = current_structure
                continue
            if state.shift_index is not None and i <= state.shift_index:
                previous_structure = current_structure
                continue

            level = float(state.retest_level or 0)
            tolerance = level_tolerance_points * point
            touched = float(candle["low"]) <= level + tolerance and float(candle["high"]) >= level - tolerance
            if touched:
                state.retest_touched = True
                if state.direction == "buy":
                    rejection = float(candle["close"]) > level
                    if require_directional_rejection:
                        rejection = rejection and float(candle["close"]) > float(candle["open"])
                else:
                    rejection = float(candle["close"]) < level
                    if require_directional_rejection:
                        rejection = rejection and float(candle["close"]) < float(candle["open"])
                if rejection:
                    if i != latest_index:
                        state.state = "SIGNAL_RESET"
                        previous_structure = current_structure
                        continue
                    direction = "BUY" if state.direction == "buy" else "SELL"
                    entry = _quote_price(data, direction, float(candle["close"]))
                    stop_ref = float(state.structural_stop or (candle["low"] if direction == "BUY" else candle["high"]))
                    sl = stop_ref - stop_buffer_points * point if direction == "BUY" else stop_ref + stop_buffer_points * point
                    stops_level = float((data.get("symbol_info") or {}).get("trade_stops_level") or 0) * point
                    if direction == "BUY" and entry - sl < stops_level:
                        sl = entry - (stops_level + stop_buffer_points * point)
                    if direction == "SELL" and sl - entry < stops_level:
                        sl = entry + (stops_level + stop_buffer_points * point)
                    risk = (entry - sl) if direction == "BUY" else (sl - entry)
                    if risk <= max(point, 0):
                        return _signal(key, stage="BLOCKED_RISK", reason="Calculated stop distance is invalid.", rules=rules)
                    tp = entry + risk * target_rr if direction == "BUY" else entry - risk * target_rr
                    score = _stage_score(state, bias_structure, True)
                    context = {
                        "symbol": data.get("symbol"),
                        "account_login": data.get("account_login"),
                        "source_version": _meta(key).get("version"),
                        "execution_timeframe": exec_tf,
                        "bias_timeframe": bias_tf,
                        "structure": current_structure,
                        "bias": bias_structure,
                        "break_level": level,
                        "structural_stop": state.structural_stop,
                        "management": dict(management or {}),
                    }
                    sig = _signal(
                        key,
                        decision=direction,
                        direction=direction,
                        stage="READY",
                        score=score,
                        reason=f"{_meta(key)['name']} break → structure shift → later retest sequence confirmed.",
                        entry=entry,
                        sl=sl,
                        tp=tp,
                        risk_percent=risk_percent,
                        source_time=int(candle["time"]),
                        rules={**rules, "trendline_break": True, "structure_shift": True, "later_retest": True, "rejection": True},
                        context=context,
                    )
                    sig.signal_key = f"{key}:{data.get('account_login', 0)}:{data.get('symbol', '')}:{int(candle['time'])}:{direction}"
                    return sig
                last_reason = "Retest touched the broken level, but the rejection candle is not confirmed yet."
                state.last_reason = last_reason

        previous_structure = current_structure

    stage = state.state if state.state != "SIGNAL_RESET" else "SCANNING"
    if stage == "WAITING_STRUCTURE_SHIFT":
        reason = state.last_reason or "Trendline break confirmed; waiting for protected structure to break."
    elif stage == "WAITING_RETEST":
        reason = state.last_reason or "Structure shift confirmed; waiting for a later retest and rejection."
    else:
        reason = last_reason if last_reason != "Waiting for a valid execution structure." else (
            f"{exec_tf} structure is {latest_structure}; waiting for the opposing trendline break."
        )
    return _signal(
        key,
        stage=stage,
        score=_stage_score(state, latest_bias),
        reason=reason,
        rules={
            **rules,
            "trendline_break": bool(state.trendline),
            "structure_shift": state.shift_index is not None,
            "later_retest": bool(state.retest_touched),
            "execution_structure": latest_structure,
            "bias_structure": latest_bias,
            "execution_structure_reason": latest_structure_reason,
            "bias_reason": latest_bias_reason,
        },
        context={
            "symbol": data.get("symbol"),
            "account_login": data.get("account_login"),
            "execution_timeframe": exec_tf,
            "bias_timeframe": bias_tf,
            "break_level": state.retest_level,
            "protected_structure": state.protected_structure,
            "structural_stop": state.structural_stop,
            "management": dict(management or {}),
        },
    )


def evaluate_human_apostle(data: dict[str, Any]) -> NativeSignal:
    return _evaluate_reversal(
        data,
        key="human_apostle",
        exec_tf="M15",
        bias_tf="H4",
        lookback=250,
        swing_strength=2,
        level_tolerance_points=50,
        trendline_buffer_points=10,
        stop_buffer_points=30,
        target_rr=2.0,
        risk_percent=1.0,
        require_bias_alignment=False,
        require_directional_rejection=False,
        reset_on_exec_misalignment=True,
        max_spread_points=30,
        management={},
    )


def evaluate_dear_bruce(data: dict[str, Any]) -> NativeSignal:
    return _evaluate_reversal(
        data,
        key="dear_bruce",
        exec_tf="M5",
        bias_tf="H4",
        lookback=400,
        swing_strength=2,
        level_tolerance_points=30,
        trendline_buffer_points=10,
        stop_buffer_points=20,
        target_rr=2.0,
        risk_percent=1.0,
        require_bias_alignment=True,
        require_directional_rejection=True,
        reset_on_exec_misalignment=False,
        max_spread_points=None,
        management={
            "break_even_r": 1.0,
            "partial_at_r": 0.0,
            "partial_close_percent": 50.0,
            "trail_start_r": 1.5,
            "trail_distance_r": 0.5,
        },
    )
