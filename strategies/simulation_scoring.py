"""Reusable simulation scoring helpers for contract-selection analysis."""

from strategies.market_context import clamp


def _collect_series(context):
    if isinstance(context, dict):
        return list(context.get("prices") or []), int(context.get("horizon_ticks") or 5), float(context.get("barrier_abs") or 0.0)
    return [], 5, 0.0


def score_directional_simulation(context):
    prices, horizon_ticks, barrier_abs = _collect_series(context)
    if len(prices) < max(12, horizon_ticks + 4):
        return {
            "higher_win_rate": 50.0,
            "lower_win_rate": 50.0,
            "sample_count": 0,
            "detail": "Simulation warming up",
        }

    threshold = max(barrier_abs * 0.20, float(context.get("average_abs_move", 0.0) or 0.0) * 0.35, 0.0000001)
    higher_hits = 0
    lower_hits = 0
    sample_count = 0
    for idx in range(0, len(prices) - horizon_ticks):
        start = float(prices[idx])
        end = float(prices[idx + horizon_ticks])
        delta = end - start
        sample_count += 1
        if delta >= threshold:
            higher_hits += 1
        elif delta <= -threshold:
            lower_hits += 1

    if sample_count <= 0:
        return {
            "higher_win_rate": 50.0,
            "lower_win_rate": 50.0,
            "sample_count": 0,
            "detail": "Simulation warming up",
        }

    higher_rate = clamp((higher_hits / sample_count) * 100.0, 0.0, 100.0)
    lower_rate = clamp((lower_hits / sample_count) * 100.0, 0.0, 100.0)
    return {
        "higher_win_rate": round(higher_rate, 1),
        "lower_win_rate": round(lower_rate, 1),
        "sample_count": int(sample_count),
        "detail": f"{sample_count} directional windows tested",
    }


def score_touch_no_touch_simulation(context):
    prices, horizon_ticks, barrier_abs = _collect_series(context)
    barrier_signed = float((context or {}).get("barrier_value", 0.0) or 0.0)
    if len(prices) < max(12, horizon_ticks + 4) or barrier_abs <= 0:
        return {
            "touch_win_rate": 50.0,
            "no_touch_win_rate": 50.0,
            "sample_count": 0,
            "detail": "Barrier simulation warming up",
        }

    touch_hits = 0
    no_touch_hits = 0
    sample_count = 0
    for idx in range(0, len(prices) - horizon_ticks):
        start = float(prices[idx])
        target = start + barrier_signed
        window = [float(value) for value in prices[idx + 1: idx + horizon_ticks + 1]]
        if not window:
            continue
        sample_count += 1
        touched = False
        if barrier_signed >= 0:
            touched = any(price >= target for price in window)
        else:
            touched = any(price <= target for price in window)
        if touched:
            touch_hits += 1
        else:
            no_touch_hits += 1

    if sample_count <= 0:
        return {
            "touch_win_rate": 50.0,
            "no_touch_win_rate": 50.0,
            "sample_count": 0,
            "detail": "Barrier simulation warming up",
        }

    return {
        "touch_win_rate": round(clamp((touch_hits / sample_count) * 100.0, 0.0, 100.0), 1),
        "no_touch_win_rate": round(clamp((no_touch_hits / sample_count) * 100.0, 0.0, 100.0), 1),
        "sample_count": int(sample_count),
        "detail": f"{sample_count} barrier windows tested",
    }
