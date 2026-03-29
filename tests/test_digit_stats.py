from strategies.digit_stats import calculate_cold_4_score
from strategies.jokerjoe import JokerJoeStrategy


def test_calculate_cold_4_score_returns_sorted_scores_and_gap_signal():
    digits = (
        [0] * 1
        + [1] * 1
        + [2] * 1
        + [3] * 1
        + [4] * 4
        + [5] * 4
        + [6] * 8
        + [7] * 8
        + [8] * 11
        + [9] * 11
    )
    result = calculate_cold_4_score(digits)

    assert result["coldest_4"] == [0, 1, 2, 3]
    assert result["signal_valid"] is True
    assert result["score_gap"] >= 3
    assert len(result["sorted_digits"]) == 10
    assert result["sorted_digits"][0]["digit"] == 0
    assert result["sorted_digits"][3]["digit"] == 3


def test_calculate_cold_4_score_applies_recent_hit_penalties():
    digits = [0, 1, 2, 3, 4, 5, 6, 7, 8, 8]
    result = calculate_cold_4_score(digits)

    score_8 = result["scores"][8]
    assert score_8["recent_hit_penalty"] == 18
    assert score_8["score"] >= 18


def test_jokerjoe_ui_payload_exposes_cold4_score():
    strat = JokerJoeStrategy()
    for digit in (
        [0] * 5
        + [1] * 5
        + [2] * 5
        + [3] * 5
        + [4] * 10
        + [5] * 10
        + [6] * 5
        + [7] * 5
        + [4] * 3
        + [5] * 7
        + [6] * 10
        + [7] * 10
        + [8] * 10
        + [9] * 10
    ):
        strat.on_tick({}, digit)

    payload = strat.get_ui_payload()

    assert "cold4_score" in payload
    assert payload["cold4_score"]["coldest_4"] == [0, 1, 2, 3]
    assert payload["cold4_score"]["signal_valid"] is True
