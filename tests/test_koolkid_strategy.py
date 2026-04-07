from strategies.koolkid import KoolKidStrategy
import time


def _feed_digits(strategy, digits):
    for idx, digit in enumerate(digits):
        strategy.on_tick({"symbol": "R_10", "epoch": idx, "quote": 100 + (digit / 100.0)}, int(digit))


def _feed_golden_card_digits(strategy, symbol, digits):
    for digit in digits:
        strategy.record_golden_card_tick(symbol, int(digit))


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


def test_kid2vix_returns_70_30_pair_when_2_and_3_are_cold():
    strat = KoolKidStrategy()
    digits = ([0, 1, 4, 5, 6, 7, 8, 9] * 3) + [0, 1, 4, 5]

    _feed_digits(strat, digits)
    strat.kid2vix_auto = True
    strat.current_auto_stake = 10.0

    analysis = strat._refresh_kid2vix_analysis()
    signals = strat.check_kid2vix_signal()

    assert analysis["label"] == "SAFE"
    assert analysis["trade_ready"] is True
    assert signals == [
        {"mode": "KID2VIX", "type": "OVER", "barrier": 3, "stake": 7.0, "duration": 1, "duration_unit": "t"},
        {"mode": "KID2VIX", "type": "UNDER", "barrier": 2, "stake": 3.0, "duration": 1, "duration_unit": "t"},
    ]


def test_kid2vix_waits_for_current_pair_and_applies_loss_cooldown():
    strat = KoolKidStrategy()
    digits = ([0, 1, 4, 5, 6, 7, 8, 9] * 3) + [0, 1, 4, 5]

    _feed_digits(strat, digits)
    strat.kid2vix_auto = True
    strat.current_auto_stake = 10.0
    strat.kid2vix_cooldown_after_loss = 9.0

    signals = strat.check_kid2vix_signal()
    assert signals is not None

    for sig in signals:
        strat.on_auto_trade_sent(sig)

    assert strat.kid2vix_cycle_active is True
    assert strat.kid2vix_open_contracts == 2
    assert strat.check_kid2vix_signal() is None

    strat.on_contract_settled({"profit": -1.0}, meta={"mode": "KID2VIX"})
    assert strat.kid2vix_cycle_active is True
    assert strat.kid2vix_open_contracts == 1

    strat.on_contract_settled({"profit": -1.0}, meta={"mode": "KID2VIX"})
    assert strat.kid2vix_cycle_active is False
    assert strat.kid2vix_open_contracts == 0
    assert strat.kid2vix_last_result == "LOSS"
    assert strat.kid2vix_cooldown_until > time.time()
    assert strat.check_kid2vix_signal() is None


def test_over_analysis_uses_over3_setup_but_places_selected_over_barrier():
    strat = KoolKidStrategy()
    digits = ([9] * 60) + ([0] * 30) + [9, 8, 7, 6, 5, 4, 3, 8, 7, 6]

    _feed_digits(strat, digits)
    strat.set_over3_analysis_barrier(1)
    strat.over3_analysis_auto = True

    state = strat.get_over3_analysis_state()
    signal = strat.check_over3_analysis_signal()

    assert state["entry_conditions_ready"] is True
    assert state["selected_barrier"] == 1
    assert state["analysis_barrier"] == 3
    assert signal == {
        "mode": "OVER3_ANALYSIS",
        "type": "OVER",
        "barrier": 1,
        "duration": 2,
        "duration_unit": "t",
        "symbol": "R_10",
    }


def test_over_analysis_toggle_waits_for_fresh_signal_before_firing():
    strat = KoolKidStrategy()
    digits = ([9] * 60) + ([0] * 30) + [9, 8, 7, 6, 5, 4, 3, 8, 7, 6]

    _feed_digits(strat, digits)
    assert strat.get_over3_analysis_state()["entry_conditions_ready"] is True

    assert strat.toggle_over3_analysis_auto() is True
    assert strat.over3_wait_fresh_setup is True
    assert strat.check_over3_analysis_signal() is None

    _feed_digits(strat, [0, 0, 0, 0, 0, 0])
    assert strat.check_over3_analysis_signal() is None
    assert strat.over3_wait_fresh_setup is False

    _feed_digits(strat, [9, 8, 7, 6, 5, 0, 9, 8, 7, 6])
    ready_state = strat.get_over3_analysis_state()
    signal = strat.check_over3_analysis_signal()

    assert signal == {
        "mode": "OVER3_ANALYSIS",
        "type": "OVER",
        "barrier": 3,
        "duration": int(ready_state["duration_ticks"]),
        "duration_unit": "t",
        "symbol": "R_10",
    }


def test_golden_card_scan_ranks_markets_and_assigns_confidence_digits():
    strat = KoolKidStrategy()
    strat.start_golden_card_scan(symbols=["R_75", "R_10", "R_25", "R_50"], history_target=20)

    _feed_golden_card_digits(strat, "R_75", ([9] * 9) + [0] + ([9] * 9) + [0])
    _feed_golden_card_digits(strat, "R_10", ([9] * 8) + ([0] * 2) + ([9] * 8) + ([0] * 2))
    _feed_golden_card_digits(strat, "R_25", ([9] * 6) + ([0] * 4) + ([9] * 6) + ([0] * 4))
    _feed_golden_card_digits(strat, "R_50", ([9] * 4) + ([0] * 6) + ([9] * 4) + ([0] * 6))

    data = strat.get_golden_card_state()
    results = data["results"]

    assert data["running"] is True
    assert data["completed_markets"] == 4
    assert [row["symbol"] for row in results[:4]] == ["R_75", "R_10", "R_25", "R_50"]
    assert [row["setup_digit"] for row in results[:4]] == [0, 1, 2, 3]
    assert results[0]["market_label"] == "V75"
    assert results[1]["market_label"] == "V10"
    assert results[0]["confidence_pct"] >= 90.0
    assert 80.0 <= results[1]["confidence_pct"] < 90.0
    assert 60.0 <= results[2]["confidence_pct"] < 80.0
    assert results[3]["confidence_pct"] < 60.0


def test_golden_card_payload_is_exposed_in_ui_payload():
    strat = KoolKidStrategy()
    strat.start_golden_card_scan(symbols=["R_10"], history_target=20)
    _feed_golden_card_digits(strat, "R_10", ([9] * 8) + ([0] * 2) + ([9] * 8) + ([0] * 2))

    payload = strat.get_ui_payload()

    assert "golden_card_data" in payload
    assert payload["golden_card_data"]["results"][0]["symbol"] == "R_10"


def test_golden_card_keeps_scanning_after_first_20_ticks_and_rolls_forward():
    strat = KoolKidStrategy()
    strat.start_golden_card_scan(symbols=["R_10"], history_target=20)

    _feed_golden_card_digits(strat, "R_10", ([9] * 8) + ([0] * 2) + ([9] * 8) + ([0] * 2))
    first = strat.get_golden_card_state()
    first_confidence = first["results"][0]["confidence_pct"]

    _feed_golden_card_digits(strat, "R_10", ([0] * 20))
    second = strat.get_golden_card_state()
    second_row = second["results"][0]

    assert first["running"] is True
    assert second["running"] is True
    assert second["completed"] is False
    assert second_row["ticks_ready"] == 20
    assert second_row["confidence_pct"] < first_confidence
    assert "live golden card scan running" in second["status"].lower()
