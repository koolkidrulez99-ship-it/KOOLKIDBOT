from strategies.koolkid_confidence import compute_koolkid_confidence_bars, assess_contract_loss_guard


def test_over_confidence_stays_strong_when_win_zone_is_active_and_losing_digits_are_quiet():
    ticks = ([7] * 18) + ([6] * 12) + ([5] * 10) + ([4] * 10)

    scores = compute_koolkid_confidence_bars(ticks)

    assert scores["over1"]["confidence_pct"] >= 80.0
    assert scores["over2"]["confidence_pct"] >= 65.0


def test_recent_hot_losing_digits_can_override_good_bigger_windows():
    calm_ticks = ([7] * 18) + ([6] * 12) + ([5] * 10) + ([4] * 10)
    danger_ticks = ([7] * 25) + ([6] * 10) + ([5] * 10) + [0, 1, 0, 1, 0]

    calm_scores = compute_koolkid_confidence_bars(calm_ticks)
    danger_scores = compute_koolkid_confidence_bars(danger_ticks)

    assert calm_scores["over1"]["confidence_pct"] > danger_scores["over1"]["confidence_pct"]
    assert danger_scores["over1"]["confidence_pct"] < 55.0


def test_under9_confidence_drops_hard_when_digit_9_turns_hot():
    calm_ticks = ([4] * 24) + ([3] * 12) + ([2] * 8) + ([1] * 4) + ([9] * 2)
    hot_nine_ticks = ([4] * 20) + ([3] * 12) + ([2] * 8) + ([1] * 5) + [9, 9, 4, 9, 9]

    calm_scores = compute_koolkid_confidence_bars(calm_ticks)
    hot_scores = compute_koolkid_confidence_bars(hot_nine_ticks)

    assert calm_scores["under9"]["confidence_pct"] > hot_scores["under9"]["confidence_pct"]
    assert hot_scores["under9"]["confidence_pct"] < 55.0


def test_loss_guard_blocks_when_losing_digits_turn_hot():
    ticks = ([9] * 45) + [5, 4, 3, 2, 0, 1, 0, 1, 9]

    guard = assess_contract_loss_guard(ticks, "over1")

    assert guard["blocked"] is True
    assert guard["lose_hits_5"] >= 2
    assert "0/1" in guard["reason"]
