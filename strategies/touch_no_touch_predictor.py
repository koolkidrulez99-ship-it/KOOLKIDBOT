"""Reusable Touch / No Touch probability analysis."""

from strategies.market_context import build_market_context, clamp
from strategies.simulation_scoring import score_touch_no_touch_simulation


CATEGORY_WEIGHTS = {
    "simulation": 0.30,
    "barrier_distance": 0.25,
    "speed_push": 0.20,
    "persistence": 0.15,
    "market_quality": 0.10,
}


def _normalize_scores(touch_raw, no_touch_raw):
    total = max(0.000001, float(touch_raw or 0.0) + float(no_touch_raw or 0.0))
    touch_pct = clamp((float(touch_raw or 0.0) / total) * 100.0, 0.0, 100.0)
    no_touch_pct = clamp(100.0 - touch_pct, 0.0, 100.0)
    return round(touch_pct, 1), round(no_touch_pct, 1)


def _confidence_label(confidence):
    value = float(confidence or 0.0)
    if value >= 75.0:
        return "Strong"
    if value >= 65.0:
        return "Good"
    if value >= 60.0:
        return "Weak"
    return "Skip"


def _suggest_action(touch_pct, no_touch_pct):
    gap = abs(float(touch_pct or 0.0) - float(no_touch_pct or 0.0))
    if touch_pct >= 60.0 and gap >= 10.0:
        return "Take Touch", gap
    if no_touch_pct >= 60.0 and gap >= 10.0:
        return "Take No Touch", gap
    return "Skip", gap


def _model_confidence(best_percent, gap, winning_scores):
    quality_mean = sum(float(v or 0.0) for v in winning_scores) / max(1, len(winning_scores))
    gap_score = clamp(float(gap or 0.0) * 5.0, 0.0, 100.0)
    confidence = (float(best_percent or 0.0) * 0.70) + (quality_mean * 0.15) + (gap_score * 0.15)
    return round(clamp(confidence, 0.0, 100.0), 1)


def predict_touch_no_touch_percentages(
    *,
    market_symbol,
    duration,
    duration_unit="t",
    prices,
    tick_times=None,
    barrier_value=None,
):
    context = build_market_context(
        market_symbol=market_symbol,
        duration=duration,
        duration_unit=duration_unit,
        prices=prices,
        tick_times=tick_times,
        barrier_value=barrier_value,
        analysis_window=30,
    )
    series = list(context.get("prices") or [])
    if len(series) < 12 or float(context.get("barrier_abs") or 0.0) <= 0:
        return {
            "market": str(market_symbol or "").upper(),
            "duration": duration,
            "duration_unit": str(duration_unit or "t").lower(),
            "status": "error",
            "message": "Not enough market history to build Touch / No Touch prediction",
        }

    deltas = list(context.get("deltas") or [])
    sign = 1.0 if float(context.get("barrier_value") or 0.0) >= 0 else -1.0
    toward_deltas = [float(delta) * sign for delta in deltas]
    recent_toward = toward_deltas[-5:]
    previous_toward = toward_deltas[-10:-5]
    average_abs_move = float(context.get("average_abs_move") or 0.0)
    average_tick_seconds = float(context.get("average_tick_seconds") or 2.0)
    horizon_ticks = int(context.get("horizon_ticks") or 5)
    barrier_distance_ratio = float(context.get("barrier_distance_ratio") or 0.0)
    chop_ratio = float(context.get("chop_ratio") or 1.0)
    spike_ratio = float(context.get("spike_ratio") or 0.0)
    net_progress_toward = (float(context.get("net_move") or 0.0) * sign)

    simulation = score_touch_no_touch_simulation(context)
    sim_touch = float(simulation.get("touch_win_rate", 50.0) or 50.0)
    sim_no_touch = float(simulation.get("no_touch_win_rate", 50.0) or 50.0)

    touch_distance = clamp(100.0 - (barrier_distance_ratio * 45.0), 8.0, 96.0)
    no_touch_distance = clamp(20.0 + (barrier_distance_ratio * 42.0), 8.0, 96.0)

    toward_ratio = (sum(1 for delta in recent_toward if delta > 0) / max(1, len(recent_toward))) if recent_toward else 0.5
    away_ratio = (sum(1 for delta in recent_toward if delta < 0) / max(1, len(recent_toward))) if recent_toward else 0.5
    speed_factor = clamp((average_abs_move / max(0.000001, float(context.get("barrier_abs") or 0.0))) * horizon_ticks * 28.0, 0.0, 100.0)
    push_factor = clamp((toward_ratio * 70.0) + (max(0.0, net_progress_toward) * 25.0 / max(0.000001, float(context.get("barrier_abs") or 0.0))), 0.0, 100.0)
    calm_factor = clamp((away_ratio * 65.0) + ((1.0 - min(1.0, speed_factor / 100.0)) * 35.0), 0.0, 100.0)
    touch_speed_push = clamp((speed_factor * 0.45) + (push_factor * 0.55), 8.0, 98.0)
    no_touch_speed_push = clamp((calm_factor * 0.55) + ((100.0 - push_factor) * 0.45), 8.0, 98.0)

    previous_push = (sum(1 for delta in previous_toward if delta > 0) / max(1, len(previous_toward))) if previous_toward else toward_ratio
    previous_away = (sum(1 for delta in previous_toward if delta < 0) / max(1, len(previous_toward))) if previous_toward else away_ratio
    touch_persistence = clamp((toward_ratio * 60.0) + (previous_push * 40.0), 8.0, 98.0)
    no_touch_persistence = clamp((away_ratio * 60.0) + (previous_away * 40.0), 8.0, 98.0)

    touch_quality = clamp((100.0 - (chop_ratio * 40.0)) + min(18.0, speed_factor * 0.18) - max(0.0, (spike_ratio - 3.0) * 6.0), 8.0, 98.0)
    no_touch_quality = clamp((100.0 - min(65.0, speed_factor * 0.45)) + (away_ratio * 16.0) - max(0.0, (spike_ratio - 2.8) * 8.0), 8.0, 98.0)

    touch_raw = (
        sim_touch * CATEGORY_WEIGHTS["simulation"]
        + touch_distance * CATEGORY_WEIGHTS["barrier_distance"]
        + touch_speed_push * CATEGORY_WEIGHTS["speed_push"]
        + touch_persistence * CATEGORY_WEIGHTS["persistence"]
        + touch_quality * CATEGORY_WEIGHTS["market_quality"]
    )
    no_touch_raw = (
        sim_no_touch * CATEGORY_WEIGHTS["simulation"]
        + no_touch_distance * CATEGORY_WEIGHTS["barrier_distance"]
        + no_touch_speed_push * CATEGORY_WEIGHTS["speed_push"]
        + no_touch_persistence * CATEGORY_WEIGHTS["persistence"]
        + no_touch_quality * CATEGORY_WEIGHTS["market_quality"]
    )

    touch_pct, no_touch_pct = _normalize_scores(touch_raw, no_touch_raw)
    preferred_side = "TOUCH" if touch_pct >= no_touch_pct else "NO_TOUCH"
    best_percent = touch_pct if preferred_side == "TOUCH" else no_touch_pct
    suggested_action, gap = _suggest_action(touch_pct, no_touch_pct)
    winning_scores = (
        [sim_touch, touch_distance, touch_speed_push, touch_persistence, touch_quality]
        if preferred_side == "TOUCH"
        else [sim_no_touch, no_touch_distance, no_touch_speed_push, no_touch_persistence, no_touch_quality]
    )
    model_confidence = _model_confidence(best_percent, gap, winning_scores)
    confidence_label = _confidence_label(model_confidence)
    model_valid = bool(best_percent >= 60.0 and gap >= 10.0 and model_confidence >= 60.0)

    if suggested_action == "Skip":
        summary = (
            f"{market_symbol}: Touch / No Touch edge is not clean enough yet "
            f"({touch_pct:.1f}% / {no_touch_pct:.1f}%, gap {gap:.1f}%)."
        )
    elif preferred_side == "TOUCH":
        summary = f"{market_symbol}: barrier is close enough to favor Touch with readable push and sim agreement."
    else:
        summary = f"{market_symbol}: barrier looks avoidable for this duration with calmer path and sim agreement."

    return {
        "status": "success",
        "market": str(market_symbol or "").upper(),
        "duration": duration,
        "duration_unit": str(duration_unit or "t").lower(),
        "horizon_ticks": int(context.get("horizon_ticks") or 5),
        "barrier": barrier_value,
        "touch_pct": float(touch_pct),
        "no_touch_pct": float(no_touch_pct),
        "higher_pct": float(touch_pct),
        "lower_pct": float(no_touch_pct),
        "preferred_side": preferred_side,
        "side_confidence": float(best_percent),
        "model_confidence": float(model_confidence),
        "confidence_label": confidence_label,
        "suggested_action": suggested_action,
        "gap": float(round(gap, 1)),
        "model_valid": model_valid,
        "reasoning_summary": summary,
        "simulation": {
            "touch_win_rate": float(sim_touch),
            "no_touch_win_rate": float(sim_no_touch),
            "sample_count": int(simulation.get("sample_count", 0)),
            "detail": simulation.get("detail"),
        },
        "score_breakdown": {
            "barrier_distance": {
                "weight": CATEGORY_WEIGHTS["barrier_distance"],
                "touch_score": round(float(touch_distance), 1),
                "no_touch_score": round(float(no_touch_distance), 1),
                "detail": f"barrier distance ratio {barrier_distance_ratio:.2f}",
            },
            "speed_push": {
                "weight": CATEGORY_WEIGHTS["speed_push"],
                "touch_score": round(float(touch_speed_push), 1),
                "no_touch_score": round(float(no_touch_speed_push), 1),
                "detail": f"speed {speed_factor:.1f} / toward ratio {toward_ratio:.2f}",
            },
            "persistence": {
                "weight": CATEGORY_WEIGHTS["persistence"],
                "touch_score": round(float(touch_persistence), 1),
                "no_touch_score": round(float(no_touch_persistence), 1),
                "detail": f"signal held over 2 checks ({previous_push:.2f} -> {toward_ratio:.2f})",
            },
            "simulation": {
                "weight": CATEGORY_WEIGHTS["simulation"],
                "touch_score": round(float(sim_touch), 1),
                "no_touch_score": round(float(sim_no_touch), 1),
                "detail": simulation.get("detail"),
            },
            "market_quality": {
                "weight": CATEGORY_WEIGHTS["market_quality"],
                "touch_score": round(float(touch_quality), 1),
                "no_touch_score": round(float(no_touch_quality), 1),
                "detail": f"chop {chop_ratio:.2f} / spike {spike_ratio:.2f}",
            },
        },
    }
