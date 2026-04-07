from collections import Counter


KOOLKID_CONFIDENCE_CONTRACTS = {
    "over2": {
        "win_digits": {3, 4, 5, 6, 7, 8, 9},
        "lose_digits": {0, 1, 2},
        "hot_multiplier": 1.2,
        "recent_hot_threshold": 2,
        "window_hot_threshold": 4,
    },
    "over1": {
        "win_digits": {2, 3, 4, 5, 6, 7, 8, 9},
        "lose_digits": {0, 1},
        "hot_multiplier": 1.25,
        "recent_hot_threshold": 2,
        "window_hot_threshold": 4,
    },
    "under9": {
        "win_digits": {0, 1, 2, 3, 4, 5, 6, 7, 8},
        "lose_digits": {9},
        "hot_multiplier": 1.5,
        "recent_hot_threshold": 2,
        "window_hot_threshold": 3,
    },
    "under8": {
        "win_digits": {0, 1, 2, 3, 4, 5, 6, 7},
        "lose_digits": {8, 9},
        "hot_multiplier": 1.35,
        "recent_hot_threshold": 2,
        "window_hot_threshold": 4,
    },
}


def _clean_digits(ticks):
    cleaned = []
    for tick in list(ticks or []):
        try:
            digit = int(tick)
        except Exception:
            continue
        if 0 <= digit <= 9:
            cleaned.append(digit)
    return cleaned


def _window(values, size):
    if size <= 0:
        return []
    return list(values[-size:])


def _ratio_score(values, target_digits):
    window = list(values or [])
    if not window:
        return 0.0
    hits = sum(1 for digit in window if digit in target_digits)
    return max(0.0, min(100.0, (hits / float(len(window))) * 100.0))


def _losing_pressure_score(last20, last5, lose_digits):
    lose20 = _ratio_score(last20, lose_digits)
    lose5 = _ratio_score(last5, lose_digits)
    return max(0.0, min(100.0, (lose20 * 0.45) + (lose5 * 0.55)))


def _max_streak(values, target_digits):
    best = 0
    current = 0
    for digit in list(values or []):
        if digit in target_digits:
            current += 1
            if current > best:
                best = current
        else:
            current = 0
    return int(best)


def _trailing_streak(values, target_digits):
    current = 0
    for digit in reversed(list(values or [])):
        if digit in target_digits:
            current += 1
        else:
            break
    return int(current)


def _hot_digit_penalty(last20, last5, lose_digits, config):
    recent_counts = Counter(digit for digit in last5 if digit in lose_digits)
    window_counts = Counter(digit for digit in last20 if digit in lose_digits)
    total_recent_hits = sum(recent_counts.values())
    total_tail_hits = sum(1 for digit in _window(last5, 3) if digit in lose_digits)
    max_recent_streak = _max_streak(last5, lose_digits)
    trailing_recent_streak = _trailing_streak(last5, lose_digits)
    multiplier = float(config.get("hot_multiplier", 1.0) or 1.0)
    recent_hot_threshold = int(config.get("recent_hot_threshold", 2) or 2)
    window_hot_threshold = int(config.get("window_hot_threshold", 4) or 4)

    penalty = 0.0

    if total_recent_hits >= 2:
        penalty += (5.0 + ((total_recent_hits - 2) * 4.0)) * multiplier
    if total_recent_hits >= 3:
        penalty += 6.0 * multiplier

    if total_tail_hits >= 2:
        penalty += 8.0 * multiplier

    if max_recent_streak >= 2:
        penalty += (7.0 + ((max_recent_streak - 2) * 4.0)) * multiplier
    if trailing_recent_streak >= 2:
        penalty += (10.0 + ((trailing_recent_streak - 2) * 5.0)) * multiplier

    for digit in lose_digits:
        if recent_counts.get(digit, 0) >= recent_hot_threshold:
            penalty += (7.0 + ((recent_counts[digit] - recent_hot_threshold) * 4.0)) * multiplier
        if window_counts.get(digit, 0) >= window_hot_threshold:
            penalty += (4.0 + ((window_counts[digit] - window_hot_threshold) * 2.5)) * multiplier

    return max(0.0, penalty)


def compute_contract_confidence(ticks, contract_key):
    config = KOOLKID_CONFIDENCE_CONTRACTS[str(contract_key).lower()]
    digits = _clean_digits(ticks)
    last50 = _window(digits, 50)
    last20 = _window(digits, 20)
    last5 = _window(digits, 5)
    win_digits = set(config["win_digits"])
    lose_digits = set(config["lose_digits"])

    zone_frequency_50_score = _ratio_score(last50, win_digits)
    zone_frequency_20_score = _ratio_score(last20, win_digits)
    recent_5tick_pressure_score = _ratio_score(last5, win_digits)
    losing_digit_pressure_score = _losing_pressure_score(last20, last5, lose_digits)
    hot_penalty = _hot_digit_penalty(last20, last5, lose_digits, config)

    confidence = (
        (0.35 * zone_frequency_50_score)
        + (0.30 * zone_frequency_20_score)
        + (0.20 * recent_5tick_pressure_score)
        - (0.15 * losing_digit_pressure_score)
    )
    confidence -= hot_penalty
    confidence = round(max(0.0, min(100.0, confidence)), 1)

    return {
        "confidence_pct": confidence,
        "zone_frequency_50_score": round(zone_frequency_50_score, 1),
        "zone_frequency_20_score": round(zone_frequency_20_score, 1),
        "recent_5tick_pressure_score": round(recent_5tick_pressure_score, 1),
        "losing_digit_pressure_score": round(losing_digit_pressure_score, 1),
        "hot_penalty": round(hot_penalty, 1),
    }


def compute_koolkid_confidence_bars(ticks):
    return {
        key: compute_contract_confidence(ticks, key)
        for key in ("over2", "over1", "under9", "under8")
    }
