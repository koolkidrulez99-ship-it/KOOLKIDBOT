"""AI contract selector that compares Higher/Lower vs Touch/No Touch."""

from strategies.higher_lower_predictor import predict_higher_lower_percentages
from strategies.market_context import build_market_context
from strategies.touch_no_touch_predictor import predict_touch_no_touch_percentages


VALID_MODES = {"AUTO_SELECT", "HIGHER_LOWER_ONLY", "TOUCH_NO_TOUCH_ONLY"}


def normalize_contract_selector_mode(value):
    mode = str(value or "AUTO_SELECT").strip().upper().replace("-", "_").replace("/", "_").replace(" ", "_")
    if mode in ("AUTO", "AUTOSELECT"):
        mode = "AUTO_SELECT"
    if mode in ("HL_ONLY", "HIGHERLOWER_ONLY"):
        mode = "HIGHER_LOWER_ONLY"
    if mode in ("TNT_ONLY", "TOUCHNOTOUCH_ONLY"):
        mode = "TOUCH_NO_TOUCH_ONLY"
    if mode not in VALID_MODES:
        return "AUTO_SELECT"
    return mode


def contract_selector_mode_label(value):
    mode = normalize_contract_selector_mode(value)
    if mode == "HIGHER_LOWER_ONLY":
        return "HIGHER / LOWER ONLY"
    if mode == "TOUCH_NO_TOUCH_ONLY":
        return "TOUCH / NO TOUCH ONLY"
    return "AUTO SELECT"


def _selector_confidence_label(confidence):
    value = float(confidence or 0.0)
    if value >= 75.0:
        return "Strong"
    if value >= 65.0:
        return "Good"
    if value >= 60.0:
        return "Weak"
    return "Skip"


def _build_final_reason(chosen_contract, chosen_side, context, hl_result, tnt_result):
    if chosen_contract == "HIGHER / LOWER":
        detail = str((hl_result or {}).get("reasoning_summary") or "").strip()
        if detail:
            return detail
        return f"{context.get('market')}: directional pressure is clearer than barrier behavior right now."
    if chosen_contract == "TOUCH / NO TOUCH":
        detail = str((tnt_result or {}).get("reasoning_summary") or "").strip()
        if detail:
            return detail
        return f"{context.get('market')}: barrier behavior looks cleaner than expiry-finish direction right now."
    return f"{context.get('market')}: both contract models are too weak right now, so skipping is safer."


def _selected_action(contract_type, side):
    if contract_type == "HIGHER / LOWER":
        return "TAKE HIGHER" if side == "HIGHER" else "TAKE LOWER"
    if contract_type == "TOUCH / NO TOUCH":
        return "TAKE TOUCH" if side == "TOUCH" else "TAKE NO TOUCH"
    return "SKIP"


def analyze_contract_selector(
    *,
    market_symbol,
    duration,
    duration_unit="t",
    prices,
    tick_times=None,
    hl_barrier_value=None,
    tnt_barrier_value=None,
    mode="AUTO_SELECT",
):
    context = build_market_context(
        market_symbol=market_symbol,
        duration=duration,
        duration_unit=duration_unit,
        prices=prices,
        tick_times=tick_times,
        barrier_value=tnt_barrier_value if tnt_barrier_value not in (None, "") else hl_barrier_value,
        analysis_window=30,
    )

    if int(context.get("available_ticks") or 0) < 12:
        return {
            "status": "error",
            "market": str(market_symbol or "").upper(),
            "mode": normalize_contract_selector_mode(mode),
            "mode_label": contract_selector_mode_label(mode),
            "message": "Not enough recent market data for contract selection",
        }

    hl_result = predict_higher_lower_percentages(
        market_symbol=market_symbol,
        duration=duration,
        duration_unit=duration_unit,
        prices=prices,
        tick_times=tick_times,
        barrier_value=hl_barrier_value,
    )
    tnt_result = predict_touch_no_touch_percentages(
        market_symbol=market_symbol,
        duration=duration,
        duration_unit=duration_unit,
        prices=prices,
        tick_times=tick_times,
        barrier_value=tnt_barrier_value,
    )

    normalized_mode = normalize_contract_selector_mode(mode)
    candidates = []
    if normalized_mode in ("AUTO_SELECT", "HIGHER_LOWER_ONLY") and isinstance(hl_result, dict) and hl_result.get("status") == "success":
        candidates.append({
            "contract_type": "HIGHER / LOWER",
            "side": str(hl_result.get("preferred_side") or ("HIGHER" if float(hl_result.get("higher_pct", 50.0)) >= float(hl_result.get("lower_pct", 50.0)) else "LOWER")).upper(),
            "confidence": float(hl_result.get("model_confidence", 0.0) or 0.0),
            "valid": bool(hl_result.get("model_valid")),
            "side_confidence": float(hl_result.get("side_confidence", 0.0) or 0.0),
            "gap": float(hl_result.get("gap", 0.0) or 0.0),
        })
    if normalized_mode in ("AUTO_SELECT", "TOUCH_NO_TOUCH_ONLY") and isinstance(tnt_result, dict) and tnt_result.get("status") == "success":
        candidates.append({
            "contract_type": "TOUCH / NO TOUCH",
            "side": str(tnt_result.get("preferred_side") or ("TOUCH" if float(tnt_result.get("touch_pct", 50.0)) >= float(tnt_result.get("no_touch_pct", 50.0)) else "NO_TOUCH")).upper(),
            "confidence": float(tnt_result.get("model_confidence", 0.0) or 0.0),
            "valid": bool(tnt_result.get("model_valid")),
            "side_confidence": float(tnt_result.get("side_confidence", 0.0) or 0.0),
            "gap": float(tnt_result.get("gap", 0.0) or 0.0),
        })

    valid_candidates = [item for item in candidates if item.get("valid")]
    chosen = None
    if valid_candidates:
        valid_candidates.sort(key=lambda item: (item.get("confidence", 0.0), item.get("gap", 0.0), item.get("side_confidence", 0.0)), reverse=True)
        chosen = valid_candidates[0]

    chosen_contract = chosen.get("contract_type") if chosen else "SKIP"
    chosen_side = chosen.get("side") if chosen else "SKIP"
    final_confidence = float(chosen.get("confidence", 0.0) if chosen else 0.0)
    suggestion = _selected_action(chosen_contract, chosen_side) if chosen else "SKIP"
    reason = _build_final_reason(chosen_contract, chosen_side, context, hl_result, tnt_result)

    return {
        "status": "success",
        "market": str(market_symbol or "").upper(),
        "duration": duration,
        "duration_unit": str(duration_unit or "t").lower(),
        "mode": normalized_mode,
        "mode_label": contract_selector_mode_label(normalized_mode),
        "hl_confidence": float((hl_result or {}).get("model_confidence", 0.0) or 0.0),
        "tnt_confidence": float((tnt_result or {}).get("model_confidence", 0.0) or 0.0),
        "chosen_contract_type": chosen_contract,
        "chosen_side": chosen_side,
        "direction_or_barrier_side_confidence": float(chosen.get("side_confidence", 0.0) if chosen else 0.0),
        "trade_confidence": final_confidence,
        "confidence_label": _selector_confidence_label(final_confidence),
        "suggested_action": suggestion,
        "reasoning_summary": reason,
        "trade_valid": bool(chosen),
        "available_ticks": int(context.get("available_ticks") or 0),
        "market_context": {
            "tick_speed_seconds": float(context.get("average_tick_seconds") or 0.0),
            "range_width": float(context.get("range_width") or 0.0),
            "net_move": float(context.get("net_move") or 0.0),
            "chop_ratio": float(context.get("chop_ratio") or 0.0),
            "barrier_distance_ratio": float(context.get("barrier_distance_ratio") or 0.0),
        },
        "higher_lower_model": hl_result,
        "touch_no_touch_model": tnt_result,
    }
