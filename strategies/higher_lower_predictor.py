"""Reusable Higher/Lower probability analysis for live market series."""

import math
import statistics


CATEGORY_WEIGHTS = {
    "simulation": 0.30,
    "direction": 0.25,
    "strength": 0.20,
    "persistence": 0.15,
    "market_quality": 0.10,
}


def _clamp(value, lower, upper):
    try:
        num = float(value)
    except Exception:
        num = lower
    return max(lower, min(upper, num))


def _safe_prices(prices):
    cleaned = []
    for raw in list(prices or []):
        try:
            value = float(raw)
        except Exception:
            continue
        if math.isfinite(value):
            cleaned.append(value)
    return cleaned


def _safe_tick_times(tick_times):
    cleaned = []
    for raw in list(tick_times or []):
        try:
            value = float(raw)
        except Exception:
            continue
        if math.isfinite(value):
            cleaned.append(value)
    return cleaned


def _mean(values, default=0.0):
    series = []
    for raw in list(values or []):
        try:
            value = float(raw)
        except Exception:
            continue
        if math.isfinite(value):
            series.append(value)
    if not series:
        return float(default)
    return float(sum(series) / len(series))


def _clean_barrier_value(barrier_value):
    if barrier_value in (None, ""):
        return 0.0
    raw = str(barrier_value).strip()
    if not raw:
        return 0.0
    try:
        return abs(float(raw))
    except Exception:
        return 0.0


def _infer_default_tick_seconds(market_symbol):
    symbol = str(market_symbol or "").strip().upper()
    if symbol.startswith("1HZ"):
        return 1.0
    return 2.0


def _average_tick_seconds(tick_times, market_symbol=None):
    series = _safe_tick_times(tick_times)
    if len(series) >= 2:
        intervals = []
        for idx in range(1, len(series)):
            delta = float(series[idx]) - float(series[idx - 1])
            if delta > 0:
                intervals.append(delta)
        if intervals:
            try:
                median_interval = float(statistics.median(intervals[-30:]))
            except Exception:
                median_interval = _mean(intervals[-30:], default=_infer_default_tick_seconds(market_symbol))
            return _clamp(median_interval, 0.2, 10.0)
    return _infer_default_tick_seconds(market_symbol)


def _duration_to_seconds(duration, duration_unit):
    unit = str(duration_unit or "t").strip().lower()
    try:
        value = float(duration)
    except Exception:
        value = 5.0 if unit == "t" else (15.0 if unit == "s" else 1.0)
    value = max(1.0, value)
    if unit == "h":
        return value * 3600.0
    if unit == "m":
        return value * 60.0
    if unit == "s":
        return value
    return None


def _duration_to_horizon_ticks(duration, duration_unit, tick_times=None, market_symbol=None):
    unit = str(duration_unit or "t").strip().lower()
    if unit == "t":
        try:
            return max(3, min(60, int(math.ceil(float(duration)))))
        except Exception:
            return 5
    target_seconds = _duration_to_seconds(duration, unit)
    average_tick_seconds = _average_tick_seconds(tick_times, market_symbol=market_symbol)
    if target_seconds is None or average_tick_seconds <= 0:
        return 5
    return max(3, min(60, int(math.ceil(target_seconds / average_tick_seconds))))


def _window_tail(values, size):
    size = max(1, int(size or 1))
    if len(values) <= size:
        return list(values)
    return list(values[-size:])


def _count_directional_ticks(deltas):
    up_moves = sum(1 for delta in deltas if delta > 0)
    down_moves = sum(1 for delta in deltas if delta < 0)
    flat_moves = max(0, len(deltas) - up_moves - down_moves)
    return up_moves, down_moves, flat_moves


def _window_bias(deltas):
    if not deltas:
        return 0.0
    gross = sum(abs(delta) for delta in deltas) or 1e-9
    net = sum(deltas)
    up_moves, down_moves, _flat_moves = _count_directional_ticks(deltas)
    count_bias = (up_moves - down_moves) / max(1, len(deltas))
    move_bias = net / gross
    return _clamp((count_bias * 0.6) + (move_bias * 0.4), -1.0, 1.0)


def _score_direction(deltas, horizon_ticks):
    recent_weight = 0.65 if horizon_ticks <= 5 else (0.58 if horizon_ticks <= 10 else 0.48)
    smooth_weight = 1.0 - recent_weight
    short_window = min(len(deltas), max(5, min(8, horizon_ticks)))
    medium_window = min(len(deltas), max(10, min(18, horizon_ticks * 2)))
    short_deltas = _window_tail(deltas, short_window)
    medium_deltas = _window_tail(deltas, medium_window)

    short_bias = _window_bias(short_deltas)
    medium_bias = _window_bias(medium_deltas)
    combined_bias = _clamp((short_bias * recent_weight) + (medium_bias * smooth_weight), -1.0, 1.0)

    higher_score = _clamp(50.0 + (combined_bias * 50.0), 0.0, 100.0)
    lower_score = _clamp(100.0 - higher_score, 0.0, 100.0)

    up_short, down_short, _ = _count_directional_ticks(short_deltas)
    up_medium, down_medium, _ = _count_directional_ticks(medium_deltas)
    detail = (
        f"recent bias {combined_bias:+.2f}; "
        f"last {len(short_deltas)} ticks up/down {up_short}/{down_short}; "
        f"last {len(medium_deltas)} ticks up/down {up_medium}/{down_medium}"
    )
    return higher_score, lower_score, detail


def _score_strength(prices, deltas, horizon_ticks):
    segment_size = min(len(prices), max(horizon_ticks + 1, 12))
    segment = _window_tail(prices, segment_size)
    segment_deltas = [segment[idx] - segment[idx - 1] for idx in range(1, len(segment))]
    if not segment_deltas:
        return 50.0, 50.0, "not enough movement data"

    gross_move = sum(abs(delta) for delta in segment_deltas)
    net_move = sum(segment_deltas)
    recent_avg_abs = gross_move / max(1, len(segment_deltas))
    baseline_deltas = _window_tail(deltas, max(segment_size * 2, 24))
    baseline_avg_abs = _mean([abs(delta) for delta in baseline_deltas], default=recent_avg_abs or 1e-9)
    activity_ratio = _clamp(recent_avg_abs / max(baseline_avg_abs, 1e-9), 0.0, 1.5)
    activity_score = _clamp((activity_ratio - 0.45) / 0.85, 0.0, 1.0)
    cleanliness = _clamp(abs(net_move) / max(gross_move, 1e-9), 0.0, 1.0)
    higher_force = _clamp(max(0.0, net_move) / max(gross_move, 1e-9), 0.0, 1.0)
    lower_force = _clamp(max(0.0, -net_move) / max(gross_move, 1e-9), 0.0, 1.0)

    higher_score = _clamp(100.0 * activity_score * ((higher_force * 0.7) + (cleanliness * 0.3)), 0.0, 100.0)
    lower_score = _clamp(100.0 * activity_score * ((lower_force * 0.7) + (cleanliness * 0.3)), 0.0, 100.0)
    detail = (
        f"net move {net_move:+.6f}; gross move {gross_move:.6f}; "
        f"activity {activity_ratio:.2f}x baseline; cleanliness {cleanliness:.2f}"
    )
    return higher_score, lower_score, detail


def _score_persistence(deltas, horizon_ticks):
    short_window = min(len(deltas), max(4, min(6, horizon_ticks)))
    medium_window = min(len(deltas), max(8, min(12, horizon_ticks * 2)))
    if short_window < 3 or medium_window < 5:
        return 50.0, 50.0, "not enough persistence history"

    latest_short = _window_tail(deltas, short_window)
    previous_short = list(deltas[-(short_window * 2):-short_window]) if len(deltas) >= short_window * 2 else list(deltas[:-short_window])
    latest_medium = _window_tail(deltas, medium_window)

    windows = [latest_short, previous_short, latest_medium]
    biases = [_window_bias(window) for window in windows if window]
    if not biases:
        return 50.0, 50.0, "no persistence windows"

    higher_support = [bias for bias in biases if bias > 0.15]
    lower_support = [bias for bias in biases if bias < -0.15]
    higher_score = _clamp((len(higher_support) / len(biases)) * 70.0 + (_mean(higher_support) * 30.0), 0.0, 100.0)
    lower_score = _clamp((len(lower_support) / len(biases)) * 70.0 + (abs(_mean(lower_support)) * 30.0), 0.0, 100.0)
    detail = f"window biases {', '.join(f'{bias:+.2f}' for bias in biases)}"
    return higher_score, lower_score, detail


def _score_simulation(prices, horizon_ticks, barrier_value):
    threshold = max(0.0, float(barrier_value or 0.0))
    sample_count = max(0, len(prices) - horizon_ticks)
    if sample_count <= 0:
        return 50.0, 50.0, {"sample_count": 0, "detail": "not enough history for rolling simulation"}

    max_windows = min(sample_count, 80)
    start_index = sample_count - max_windows
    recency_bonus = 0.60 if horizon_ticks <= 5 else (0.40 if horizon_ticks <= 10 else 0.25)

    higher_hits = 0.0
    lower_hits = 0.0
    for local_idx, idx in enumerate(range(start_index, sample_count)):
        start_price = float(prices[idx])
        end_price = float(prices[idx + horizon_ticks])
        delta = end_price - start_price
        progress = local_idx / max(1, max_windows - 1)
        weight = 1.0 + (recency_bonus * progress)
        if delta > threshold:
            higher_hits += weight
        elif delta < (-threshold):
            lower_hits += weight
        else:
            higher_hits += weight * 0.5
            lower_hits += weight * 0.5

    total_weight = higher_hits + lower_hits
    if total_weight <= 0:
        return 50.0, 50.0, {"sample_count": int(max_windows), "detail": "simulation produced no weighted samples"}

    higher_score = _clamp((higher_hits / total_weight) * 100.0, 0.0, 100.0)
    lower_score = _clamp((lower_hits / total_weight) * 100.0, 0.0, 100.0)
    detail = {
        "sample_count": int(max_windows),
        "threshold": float(threshold),
        "detail": f"rolling sim over {int(max_windows)} windows with {horizon_ticks}-tick horizon",
    }
    return higher_score, lower_score, detail


def _score_market_quality(prices, deltas, horizon_ticks):
    segment_size = min(len(prices), max(horizon_ticks * 2, 16))
    segment = _window_tail(prices, segment_size)
    segment_deltas = [segment[idx] - segment[idx - 1] for idx in range(1, len(segment))]
    if not segment_deltas:
        return 35.0, 35.0, "not enough market quality data"

    abs_deltas = [abs(delta) for delta in segment_deltas]
    avg_abs = _mean(abs_deltas, default=0.0)
    max_abs = max(abs_deltas) if abs_deltas else 0.0
    up_moves, down_moves, flat_moves = _count_directional_ticks(segment_deltas)
    gross_move = sum(abs_deltas)
    net_move = abs(sum(segment_deltas))
    readability = _clamp(net_move / max(gross_move, 1e-9), 0.0, 1.0)
    flip_count = 0
    prev_sign = 0
    for delta in segment_deltas:
        sign = 1 if delta > 0 else (-1 if delta < 0 else 0)
        if sign and prev_sign and sign != prev_sign:
            flip_count += 1
        if sign:
            prev_sign = sign
    flip_ratio = flip_count / max(1, len(segment_deltas) - 1)
    flat_ratio = flat_moves / max(1, len(segment_deltas))
    spike_penalty = 0.0
    if avg_abs > 0 and max_abs >= (avg_abs * 3.0):
        recent_tail = segment_deltas[-min(3, len(segment_deltas)):]
        follow_through = abs(sum(recent_tail)) / max(max_abs, 1e-9)
        if follow_through < 0.45:
            spike_penalty = 0.30

    activity_score = _clamp((avg_abs / max(_mean([abs(delta) for delta in _window_tail(deltas, max(segment_size * 2, 30))], default=avg_abs), 1e-9) - 0.4) / 0.9, 0.0, 1.0)
    quality = 100.0 * (
        (0.35 * activity_score)
        + (0.35 * readability)
        + (0.20 * (1.0 - _clamp(flip_ratio, 0.0, 1.0)))
        + (0.10 * (1.0 - _clamp(flat_ratio + spike_penalty, 0.0, 1.0)))
    )
    quality = _clamp(quality, 0.0, 100.0)
    detail = (
        f"readability {readability:.2f}; flip ratio {flip_ratio:.2f}; "
        f"flat ratio {flat_ratio:.2f}; spike penalty {spike_penalty:.2f}"
    )
    return quality, quality, detail


def _normalize_percentages(higher_raw, lower_raw):
    total = float(higher_raw or 0.0) + float(lower_raw or 0.0)
    if total <= 0:
        return 50.0, 50.0
    higher_pct = (float(higher_raw or 0.0) / total) * 100.0
    lower_pct = (float(lower_raw or 0.0) / total) * 100.0
    total_pct = higher_pct + lower_pct
    if total_pct <= 0:
        return 50.0, 50.0
    higher_pct = round((higher_pct / total_pct) * 100.0, 1)
    lower_pct = round(100.0 - higher_pct, 1)
    return higher_pct, lower_pct


def _confidence_label(best_percent):
    if best_percent >= 75.0:
        return "Strong"
    if best_percent >= 65.0:
        return "Good"
    if best_percent >= 60.0:
        return "Weak"
    return "Skip"


def _suggest_action(higher_pct, lower_pct):
    gap = abs(float(higher_pct) - float(lower_pct))
    higher_ready = float(higher_pct) >= 60.0
    lower_ready = float(lower_pct) >= 60.0
    if gap < 10.0 or (not higher_ready and not lower_ready):
        return "Skip", gap
    return ("Take Higher" if float(higher_pct) > float(lower_pct) else "Take Lower"), gap


def _model_confidence(best_percent, gap, winning_scores):
    quality_mean = sum(float(v or 0.0) for v in winning_scores) / max(1, len(winning_scores))
    gap_score = _clamp(float(gap or 0.0) * 5.0, 0.0, 100.0)
    confidence = (float(best_percent or 0.0) * 0.70) + (quality_mean * 0.15) + (gap_score * 0.15)
    return round(_clamp(confidence, 0.0, 100.0), 1)


def _duration_output_value(duration):
    raw = str(duration or "").strip()
    if not raw:
        return duration
    try:
        numeric = float(raw)
    except Exception:
        return duration
    if numeric.is_integer():
        return int(numeric)
    return numeric


def predict_higher_lower_percentages(
    *,
    market_symbol,
    duration,
    duration_unit="t",
    prices,
    tick_times=None,
    barrier_value=None,
):
    series = _safe_prices(prices)
    if len(series) < 12:
        return {
            "market": str(market_symbol or "").upper(),
            "duration": duration,
            "duration_unit": str(duration_unit or "t").lower(),
            "status": "error",
            "message": "Not enough market history to build Higher/Lower prediction",
        }

    horizon_ticks = _duration_to_horizon_ticks(
        duration,
        duration_unit,
        tick_times=tick_times,
        market_symbol=market_symbol,
    )
    horizon_ticks = max(3, min(horizon_ticks, len(series) - 1))
    deltas = [series[idx] - series[idx - 1] for idx in range(1, len(series))]
    barrier_magnitude = _clean_barrier_value(barrier_value)

    simulation_high, simulation_low, simulation_meta = _score_simulation(series, horizon_ticks, barrier_magnitude)
    direction_high, direction_low, direction_detail = _score_direction(deltas, horizon_ticks)
    strength_high, strength_low, strength_detail = _score_strength(series, deltas, horizon_ticks)
    persistence_high, persistence_low, persistence_detail = _score_persistence(deltas, horizon_ticks)
    quality_high, quality_low, quality_detail = _score_market_quality(series, deltas, horizon_ticks)

    higher_raw = (
        (simulation_high * CATEGORY_WEIGHTS["simulation"])
        + (direction_high * CATEGORY_WEIGHTS["direction"])
        + (strength_high * CATEGORY_WEIGHTS["strength"])
        + (persistence_high * CATEGORY_WEIGHTS["persistence"])
        + (quality_high * CATEGORY_WEIGHTS["market_quality"])
    )
    lower_raw = (
        (simulation_low * CATEGORY_WEIGHTS["simulation"])
        + (direction_low * CATEGORY_WEIGHTS["direction"])
        + (strength_low * CATEGORY_WEIGHTS["strength"])
        + (persistence_low * CATEGORY_WEIGHTS["persistence"])
        + (quality_low * CATEGORY_WEIGHTS["market_quality"])
    )

    higher_pct, lower_pct = _normalize_percentages(higher_raw, lower_raw)
    best_percent = max(higher_pct, lower_pct)
    suggested_action, gap = _suggest_action(higher_pct, lower_pct)
    dominant_side = "Higher" if higher_pct >= lower_pct else "Lower"
    dominant_key = "HIGHER" if dominant_side == "Higher" else "LOWER"
    winning_scores = (
        [simulation_high, direction_high, strength_high, persistence_high, quality_high]
        if dominant_key == "HIGHER"
        else [simulation_low, direction_low, strength_low, persistence_low, quality_low]
    )
    model_confidence = _model_confidence(best_percent, gap, winning_scores)
    confidence = _confidence_label(model_confidence)
    model_valid = bool(best_percent >= 60.0 and gap >= 10.0 and model_confidence >= 60.0)

    if suggested_action == "Skip":
        summary = (
            f"{market_symbol}: {dominant_side} edge is not clean enough yet "
            f"({higher_pct:.1f}% / {lower_pct:.1f}%, gap {gap:.1f}%)."
        )
    else:
        summary = (
            f"{market_symbol}: {dominant_side} has the stronger edge "
            f"({higher_pct:.1f}% / {lower_pct:.1f}%) with {confidence.lower()} confidence."
        )

    return {
        "status": "success",
        "market": str(market_symbol or "").upper(),
        "duration": _duration_output_value(duration),
        "duration_unit": str(duration_unit or "t").lower(),
        "horizon_ticks": int(horizon_ticks),
        "barrier": barrier_value,
        "higher_pct": float(higher_pct),
        "lower_pct": float(lower_pct),
        "preferred_side": dominant_key,
        "side_confidence": float(best_percent),
        "model_confidence": float(model_confidence),
        "confidence_label": confidence,
        "suggested_action": suggested_action,
        "gap": float(round(gap, 1)),
        "model_valid": model_valid,
        "reasoning_summary": summary,
        "simulation": {
            "higher_win_rate": float(round(simulation_high, 1)),
            "lower_win_rate": float(round(simulation_low, 1)),
            "sample_count": int(simulation_meta.get("sample_count", 0)),
            "detail": simulation_meta.get("detail"),
            "barrier_threshold": float(round(simulation_meta.get("threshold", 0.0), 6)),
        },
        "score_breakdown": {
            "direction": {
                "weight": CATEGORY_WEIGHTS["direction"],
                "higher_score": float(round(direction_high, 1)),
                "lower_score": float(round(direction_low, 1)),
                "detail": direction_detail,
            },
            "strength": {
                "weight": CATEGORY_WEIGHTS["strength"],
                "higher_score": float(round(strength_high, 1)),
                "lower_score": float(round(strength_low, 1)),
                "detail": strength_detail,
            },
            "persistence": {
                "weight": CATEGORY_WEIGHTS["persistence"],
                "higher_score": float(round(persistence_high, 1)),
                "lower_score": float(round(persistence_low, 1)),
                "detail": persistence_detail,
            },
            "simulation": {
                "weight": CATEGORY_WEIGHTS["simulation"],
                "higher_score": float(round(simulation_high, 1)),
                "lower_score": float(round(simulation_low, 1)),
                "detail": simulation_meta.get("detail"),
            },
            "market_quality": {
                "weight": CATEGORY_WEIGHTS["market_quality"],
                "higher_score": float(round(quality_high, 1)),
                "lower_score": float(round(quality_low, 1)),
                "detail": quality_detail,
            },
        },
        "raw_scores": {
            "higher": float(round(higher_raw, 2)),
            "lower": float(round(lower_raw, 2)),
        },
    }
