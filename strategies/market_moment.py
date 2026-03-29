import math


CHECK_WEIGHT = 25


def _clean_direction(direction):
    side = str(direction or "").strip().upper()
    return "LOWER" if side == "LOWER" else "HIGHER"


def _safe_prices(prices):
    cleaned = []
    for value in list(prices or []):
        try:
            num = float(value)
        except Exception:
            continue
        if math.isfinite(num):
            cleaned.append(num)
    return cleaned


def infer_simulation_winner(sample_deltas, movement_threshold=0.0):
    threshold = max(0.0, float(movement_threshold or 0.0))
    higher_hits = 0
    lower_hits = 0
    for raw in list(sample_deltas or []):
        try:
            delta = float(raw)
        except Exception:
            continue
        if not math.isfinite(delta):
            continue
        if delta >= threshold:
            higher_hits += 1
        if delta <= -threshold:
            lower_hits += 1
    if higher_hits > lower_hits:
        return "HIGHER"
    if lower_hits > higher_hits:
        return "LOWER"
    return "NONE"


def score_market_moment(
    *,
    direction,
    prices,
    simulation_winner=None,
    previous_snapshot=None,
    barrier_value=0.0,
    current_marker=None,
    tick_window=5,
):
    side = _clean_direction(direction)
    series = _safe_prices(prices)
    tick_window = max(3, int(tick_window or 5))
    deltas = [series[idx] - series[idx - 1] for idx in range(1, len(series))]
    recent_deltas = deltas[-tick_window:]
    up_moves = sum(1 for delta in recent_deltas if delta > 0)
    down_moves = sum(1 for delta in recent_deltas if delta < 0)
    chosen_tick_moves = up_moves if side == "HIGHER" else down_moves
    opposing_tick_moves = down_moves if side == "HIGHER" else up_moves
    tick_pass = len(recent_deltas) >= tick_window and chosen_tick_moves >= 3

    range_window = series[-max(tick_window + 1, 8):]
    if len(range_window) >= 2:
        net_move = range_window[-1] - range_window[0]
        range_width = max(range_window) - min(range_window)
    else:
        net_move = 0.0
        range_width = 0.0
    chosen_move = net_move if side == "HIGHER" else -net_move
    avg_abs_delta = (
        sum(abs(delta) for delta in recent_deltas) / len(recent_deltas)
        if recent_deltas
        else 0.0
    )
    barrier_mag = abs(float(barrier_value or 0.0))
    movement_floor = max(barrier_mag * 0.30, avg_abs_delta * 2.0, range_width * 0.18, 0.0000001)
    movement_pass = chosen_move > 0 and abs(chosen_move) >= movement_floor and avg_abs_delta > 0

    sim_winner = _clean_direction(simulation_winner) if str(simulation_winner or "").upper() in ("HIGHER", "LOWER") else "NONE"
    simulation_pass = sim_winner == side

    previous = previous_snapshot if isinstance(previous_snapshot, dict) else {}
    previous_marker = previous.get("marker")
    previous_same_cycle = current_marker is not None and previous_marker == current_marker
    previous_same_side = _clean_direction(previous.get("direction", side)) == side
    previous_core_passes = int(previous.get("core_passes", 0) or 0)
    current_core_passes = int(simulation_pass) + int(tick_pass) + int(movement_pass)
    persistence_pass = (
        current_marker not in (None, "")
        and not previous_same_cycle
        and previous_same_side
        and previous_core_passes >= 2
        and current_core_passes >= 2
    )

    checks = {
        "simulation_direction": {
            "passed": bool(simulation_pass),
            "detail": (
                f"simulation winner matched {side.lower()}"
                if simulation_pass
                else f"simulation winner was {sim_winner.lower()}" if sim_winner != "NONE" else "simulation winner was mixed"
            ),
        },
        "tick_direction": {
            "passed": bool(tick_pass),
            "detail": f"{chosen_tick_moves}/{max(len(recent_deltas), tick_window)} ticks favored {side.lower()} vs {opposing_tick_moves} opposite",
        },
        "movement_strength": {
            "passed": bool(movement_pass),
            "detail": f"net move {chosen_move:+.6f} vs floor {movement_floor:.6f}",
        },
        "signal_persistence": {
            "passed": bool(persistence_pass),
            "detail": (
                "direction held across the last 2 checks"
                if persistence_pass
                else "direction has not held across multiple checks yet"
            ),
        },
    }

    passed_checks = sum(1 for item in checks.values() if item["passed"])
    score = passed_checks * CHECK_WEIGHT
    if score >= 75 and passed_checks >= 3:
        label = "GOOD"
    elif score >= 50:
        label = "RISKY"
    else:
        label = "SKIP"

    snapshot = {
        "direction": side,
        "marker": current_marker,
        "core_passes": current_core_passes,
        "score": score,
        "label": label,
    }

    return {
        "direction": side,
        "score": score,
        "passed_checks": passed_checks,
        "checks": checks,
        "label": label,
        "simulation_winner": sim_winner,
        "up_ticks": up_moves,
        "down_ticks": down_moves,
        "movement_floor": movement_floor,
        "chosen_move": chosen_move,
        "snapshot": snapshot,
    }
