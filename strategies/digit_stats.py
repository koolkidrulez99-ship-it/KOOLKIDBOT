def _clean_digits(digits):
    cleaned = []
    for raw in list(digits or []):
        try:
            digit = int(raw)
        except Exception:
            continue
        if 0 <= digit <= 9:
            cleaned.append(digit)
    return cleaned


def calculate_cold_4_score(digits, gap_threshold=3):
    series = _clean_digits(digits)
    last_50 = series[-50:]
    last_20 = series[-20:]
    last_10 = series[-10:]
    last_2 = series[-2:]
    last_1 = series[-1:]

    scores = {}
    ranked = []
    for digit in range(10):
        freq_50 = last_50.count(digit)
        freq_20 = last_20.count(digit)
        freq_10 = last_10.count(digit)

        recent_penalty = 0
        if last_1 and last_1[-1] == digit:
            recent_penalty += 4
        if last_2.count(digit) >= 2:
            recent_penalty += 6
        if len(last_2) == 2 and last_2[0] == digit and last_2[1] == digit:
            recent_penalty += 8

        score = int((freq_50 * 1) + (freq_20 * 2) + (freq_10 * 3) + recent_penalty)
        scores[digit] = {
            "digit": digit,
            "score": score,
            "freq_50": int(freq_50),
            "freq_20": int(freq_20),
            "freq_10": int(freq_10),
            "recent_hit_penalty": int(recent_penalty),
        }
        ranked.append({"digit": digit, "score": score})

    ranked.sort(key=lambda item: (int(item["score"]), int(item["digit"])))
    coldest_4 = [int(item["digit"]) for item in ranked[:4]]
    fourth_score = int(ranked[3]["score"]) if len(ranked) >= 4 else None
    fifth_score = int(ranked[4]["score"]) if len(ranked) >= 5 else None
    score_gap = (fifth_score - fourth_score) if fourth_score is not None and fifth_score is not None else 0
    signal_valid = bool(len(coldest_4) == 4 and score_gap >= int(gap_threshold))

    return {
        "scores": scores,
        "sorted_digits": ranked,
        "coldest_4": coldest_4,
        "signal_valid": signal_valid,
        "signal_strength": "VALID" if signal_valid else "WEAK",
        "score_gap": int(score_gap),
        "gap_threshold": int(gap_threshold),
        "sample_size": int(len(series)),
    }
