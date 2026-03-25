from strategies.koolkid import KoolKidStrategy


def _feed_digits(strategy, digits):
    for idx, digit in enumerate(digits):
        strategy.on_tick({"symbol": "R_10", "epoch": idx, "quote": 100 + (digit / 100.0)}, int(digit))


def test_koolluck_background_analysis_tracks_best_candidate_while_off():
    strat = KoolKidStrategy()
    digits = ([0] * 10) + ([1] * 11) + ([2] * 11) + ([3] * 12) + ([4] * 10) + ([5] * 11) + ([6] * 11) + ([7] * 10) + ([8] * 10) + ([9] * 4)

    _feed_digits(strat, digits)

    analysis = strat.koolluck_background_analysis
    assert analysis["ready"] is True
    assert analysis["best_signal"] == {"mode": "KOOLLUCK", "type": "UNDER", "barrier": 9}
    assert analysis["best_probability"] > 60.0
    assert strat.check_koolluck_signal() is None


def test_koolluck_returns_background_candidate_when_auto_enabled():
    strat = KoolKidStrategy()
    digits = ([0] * 10) + ([1] * 11) + ([2] * 11) + ([3] * 12) + ([4] * 10) + ([5] * 11) + ([6] * 11) + ([7] * 10) + ([8] * 10) + ([9] * 4)

    _feed_digits(strat, digits)
    strat.koolluck_auto = True

    assert strat.check_koolluck_signal() == {"mode": "KOOLLUCK", "type": "UNDER", "barrier": 9}


def test_koolluck_scores_over3_as_tradable_when_upper_side_is_stronger():
    strat = KoolKidStrategy()
    digits = ([0] * 5) + ([1] * 5) + ([2] * 6) + ([3] * 7) + ([4] * 8) + ([5] * 10) + ([6] * 10) + ([7] * 12) + ([8] * 15) + ([9] * 22)

    _feed_digits(strat, digits)
    analysis = strat.koolluck_background_analysis
    over3 = next(row for row in analysis["candidates"] if row["type"] == "OVER" and row["barrier"] == 3)

    assert analysis["ready"] is True
    assert over3["qualified"] is True
    assert over3["probability"] > 60.0


def test_auto_dollar_background_analysis_tracks_leading_side_while_off():
    strat = KoolKidStrategy()
    digits = ([0] * 8) + ([1] * 8) + ([2] * 9) + ([3] * 9) + ([4] * 10) + ([5] * 11) + ([6] * 13) + ([7] * 10) + ([8] * 11) + ([9] * 11)

    _feed_digits(strat, digits)

    analysis = strat.auto_dollar_analysis
    assert analysis["ready"] is True
    assert analysis["sample_size"] == 100
    assert analysis["leading_side"] == "OVER4"
    assert analysis["over4_wins"] == 56
    assert analysis["under5_wins"] == 44
    assert analysis["split"] == {"over4": 0.6, "under5": 0.4}
    assert strat.check_auto_dollar_signal() is None


def test_auto_dollar_returns_two_weighted_signals_when_enabled():
    strat = KoolKidStrategy()
    digits = ([0] * 8) + ([1] * 8) + ([2] * 9) + ([3] * 9) + ([4] * 10) + ([5] * 11) + ([6] * 13) + ([7] * 10) + ([8] * 11) + ([9] * 11)

    _feed_digits(strat, digits)
    strat.auto_dollar_auto = True
    strat.current_auto_stake = 1.0

    signals = strat.check_auto_dollar_signal()

    assert signals == [
        {"mode": "AUTO$", "type": "OVER", "barrier": 4, "stake": 0.6},
        {"mode": "AUTO$", "type": "UNDER", "barrier": 5, "stake": 0.4},
    ]


def test_auto_dollar_uses_even_split_on_tie():
    strat = KoolKidStrategy()
    digits = ([0] * 10) + ([1] * 10) + ([2] * 10) + ([3] * 10) + ([4] * 10) + ([5] * 10) + ([6] * 10) + ([7] * 10) + ([8] * 10) + ([9] * 10)

    _feed_digits(strat, digits)
    strat.auto_dollar_auto = True
    strat.current_auto_stake = 1.0

    analysis = strat.auto_dollar_analysis
    signals = strat.check_auto_dollar_signal()

    assert analysis["leading_side"] == "TIE"
    assert analysis["split"] == {"over4": 0.5, "under5": 0.5}
    assert signals == [
        {"mode": "AUTO$", "type": "OVER", "barrier": 4, "stake": 0.5},
        {"mode": "AUTO$", "type": "UNDER", "barrier": 5, "stake": 0.5},
    ]
