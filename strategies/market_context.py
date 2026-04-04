"""Shared market context builder for contract-selection analysis."""

import math
import statistics


def clamp(value, lower, upper):
    try:
        num = float(value)
    except Exception:
        num = lower
    return max(lower, min(upper, num))


def normalize_barrier_value(value):
    if value in (None, ""):
        return 0.0
    try:
        num = float(str(value).strip())
    except Exception:
        return 0.0
    if not math.isfinite(num):
        return 0.0
    return float(num)


def safe_prices(prices):
    cleaned = []
    for raw in list(prices or []):
        try:
            value = float(raw)
        except Exception:
            continue
        if math.isfinite(value):
            cleaned.append(value)
    return cleaned


def safe_tick_times(tick_times):
    cleaned = []
    for raw in list(tick_times or []):
        try:
            value = float(raw)
        except Exception:
            continue
        if math.isfinite(value):
            cleaned.append(value)
    return cleaned


def infer_default_tick_seconds(market_symbol):
    symbol = str(market_symbol or "").upper().strip()
    if symbol.startswith("1HZ"):
        return 1.0
    return 2.0


def average_tick_seconds(tick_times, market_symbol=None):
    series = safe_tick_times(tick_times)
    if len(series) >= 2:
        deltas = []
        for idx in range(1, len(series)):
            gap = float(series[idx]) - float(series[idx - 1])
            if gap > 0:
                deltas.append(gap)
        if deltas:
            try:
                return clamp(statistics.median(deltas[-30:]), 0.2, 10.0)
            except Exception:
                pass
    return infer_default_tick_seconds(market_symbol)


def duration_to_seconds(duration, duration_unit):
    unit = str(duration_unit or "t").strip().lower()
    try:
        value = float(duration)
    except Exception:
        value = 5.0 if unit == "t" else 1.0
    value = max(1.0, value)
    if unit == "h":
        return value * 3600.0
    if unit == "m":
        return value * 60.0
    if unit == "s":
        return value
    return None


def duration_to_horizon_ticks(duration, duration_unit, tick_times=None, market_symbol=None):
    unit = str(duration_unit or "t").strip().lower()
    if unit == "t":
        try:
            return max(3, min(60, int(math.ceil(float(duration)))))
        except Exception:
            return 5
    seconds = duration_to_seconds(duration, unit)
    tick_seconds = average_tick_seconds(tick_times, market_symbol=market_symbol)
    horizon = int(math.ceil(float(seconds or 10.0) / max(0.2, tick_seconds)))
    return max(3, min(60, horizon))


def build_market_context(
    *,
    market_symbol,
    duration,
    duration_unit="t",
    prices,
    tick_times=None,
    barrier_value=None,
    analysis_window=30,
):
    series = safe_prices(prices)
    times = safe_tick_times(tick_times)
    if analysis_window and len(series) > int(analysis_window):
        series = series[-int(analysis_window):]
        if times:
            times = times[-len(series):]
    deltas = [series[idx] - series[idx - 1] for idx in range(1, len(series))]
    positive_moves = sum(1 for delta in deltas if delta > 0)
    negative_moves = sum(1 for delta in deltas if delta < 0)
    flat_moves = max(0, len(deltas) - positive_moves - negative_moves)
    current_price = series[-1] if series else None
    start_price = series[0] if series else None
    net_move = (current_price - start_price) if len(series) >= 2 else 0.0
    range_width = (max(series) - min(series)) if series else 0.0
    average_abs_move = (sum(abs(delta) for delta in deltas) / len(deltas)) if deltas else 0.0
    avg_tick_seconds = average_tick_seconds(times, market_symbol=market_symbol)
    horizon_ticks = duration_to_horizon_ticks(duration, duration_unit, tick_times=times, market_symbol=market_symbol)
    barrier_signed = normalize_barrier_value(barrier_value)
    barrier_abs = abs(barrier_signed)
    barrier_target = (current_price + barrier_signed) if current_price is not None else None
    movement_budget = max(average_abs_move * max(3, horizon_ticks), 0.000001)
    distance_ratio = barrier_abs / movement_budget if barrier_abs > 0 else 0.0
    chop_ratio = (
        min(positive_moves, negative_moves) / max(1.0, float(max(positive_moves, negative_moves)))
        if deltas
        else 1.0
    )
    spike_ratio = 0.0
    if deltas:
        max_move = max(abs(delta) for delta in deltas)
        if average_abs_move > 0:
            spike_ratio = max_move / average_abs_move

    return {
        "market": str(market_symbol or "").upper().strip(),
        "duration": duration,
        "duration_unit": str(duration_unit or "t").lower(),
        "prices": series,
        "tick_times": times,
        "deltas": deltas,
        "horizon_ticks": int(horizon_ticks),
        "current_price": current_price,
        "start_price": start_price,
        "net_move": float(net_move),
        "range_width": float(range_width),
        "average_abs_move": float(average_abs_move),
        "average_tick_seconds": float(avg_tick_seconds),
        "positive_moves": int(positive_moves),
        "negative_moves": int(negative_moves),
        "flat_moves": int(flat_moves),
        "chop_ratio": float(chop_ratio),
        "spike_ratio": float(spike_ratio),
        "barrier_value": float(barrier_signed),
        "barrier_abs": float(barrier_abs),
        "barrier_target": barrier_target,
        "barrier_distance_ratio": float(distance_ratio),
        "available_ticks": int(len(series)),
    }
