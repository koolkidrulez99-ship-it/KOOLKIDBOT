from strategies.market_moment import infer_simulation_winner, score_market_moment


def test_infer_simulation_winner_prefers_direction_with_more_hits():
    assert infer_simulation_winner([0.12, 0.09, -0.01, 0.08], movement_threshold=0.05) == "HIGHER"
    assert infer_simulation_winner([-0.11, -0.08, 0.02, -0.07], movement_threshold=0.05) == "LOWER"
    assert infer_simulation_winner([0.02, -0.02, 0.01], movement_threshold=0.05) == "NONE"


def test_score_market_moment_returns_good_when_three_checks_pass():
    moment = score_market_moment(
        direction="HIGHER",
        prices=[100.00, 100.03, 100.07, 100.12, 100.18, 100.25, 100.33],
        simulation_winner="HIGHER",
        barrier_value=0.12,
        current_marker=10,
    )

    assert moment["direction"] == "HIGHER"
    assert moment["score"] == 75
    assert moment["passed_checks"] == 3
    assert moment["label"] == "GOOD"
    assert moment["checks"]["simulation_direction"]["passed"] is True
    assert moment["checks"]["tick_direction"]["passed"] is True
    assert moment["checks"]["movement_strength"]["passed"] is True
    assert moment["checks"]["signal_persistence"]["passed"] is False


def test_score_market_moment_returns_risky_when_only_two_checks_pass():
    moment = score_market_moment(
        direction="HIGHER",
        prices=[100.00, 100.01, 100.02, 100.03, 100.04, 100.05],
        simulation_winner="HIGHER",
        barrier_value=1.0,
        current_marker=11,
    )

    assert moment["score"] == 50
    assert moment["passed_checks"] == 2
    assert moment["label"] == "RISKY"
    assert moment["checks"]["simulation_direction"]["passed"] is True
    assert moment["checks"]["tick_direction"]["passed"] is True
    assert moment["checks"]["movement_strength"]["passed"] is False
    assert moment["checks"]["signal_persistence"]["passed"] is False


def test_score_market_moment_returns_skip_when_direction_is_weak():
    moment = score_market_moment(
        direction="LOWER",
        prices=[100.00, 100.03, 100.05, 100.06, 100.08, 100.09],
        simulation_winner="HIGHER",
        barrier_value=0.12,
        current_marker=12,
    )

    assert moment["score"] == 0
    assert moment["passed_checks"] == 0
    assert moment["label"] == "SKIP"


def test_score_market_moment_requires_persistence_across_checks():
    first = score_market_moment(
        direction="HIGHER",
        prices=[100.00, 100.03, 100.07, 100.12, 100.18, 100.25, 100.33],
        simulation_winner="HIGHER",
        barrier_value=0.12,
        current_marker=20,
    )
    second = score_market_moment(
        direction="HIGHER",
        prices=[100.03, 100.07, 100.12, 100.18, 100.25, 100.33, 100.42],
        simulation_winner="HIGHER",
        previous_snapshot=first["snapshot"],
        barrier_value=0.12,
        current_marker=21,
    )

    assert first["checks"]["signal_persistence"]["passed"] is False
    assert second["checks"]["signal_persistence"]["passed"] is True
    assert second["score"] == 100
    assert second["label"] == "GOOD"
