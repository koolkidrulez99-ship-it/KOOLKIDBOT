from server import (
    _build_unchain_scanner_analysis,
    _ensure_unchain_scanner,
    _get_top_unchain_scanner_recs,
    _scanner_market_label,
)


def test_scanner_formats_market_labels_like_ui():
    assert _scanner_market_label("R_25") == "Vol 25"
    assert _scanner_market_label("1HZ90V") == "Vol 90 (1s)"


def test_scanner_defaults_to_ten_markets_over_twenty_ticks():
    scan = _ensure_unchain_scanner({})

    assert scan["max_symbols"] == 10
    assert scan["window_ticks"] == 20
    assert scan["minimum_history"] == 20
    assert scan["sample_size"] == 20


def test_scanner_uses_quarter_of_longest_average_move_for_barrier():
    prices = [100 + (4 * idx) for idx in range(22)]

    rec = _build_unchain_scanner_analysis(prices, window_ticks=20, symbol="R_25", active_symbol="R_25")

    assert rec is not None
    assert rec["display_name"] == "Vol 25"
    assert rec["is_active"] is True
    assert rec["avg_move_up"] == 76.0
    assert rec["avg_move_down"] == 0.0
    assert rec["barrier_value"] == 19.0
    assert rec["barrier_high"] == "+19.00"
    assert rec["barrier_low"] == "-19.00"
    assert rec["higher_win"] == 100.0
    assert rec["lower_win"] == 0.0
    assert rec["best_side"] == "HIGHER"


def test_scanner_ranks_by_longest_combined_movement_and_filters_short_history():
    scanner = {
        "minimum_history": 120,
        "analyses": {
            "R_10": {
                "symbol": "R_10",
                "ticks_ready": 150,
                "combined_move": 40.0,
                "higher_win_prob": 0.31,
                "lower_win_prob": 0.48,
                "is_active": False,
            },
            "R_25": {
                "symbol": "R_25",
                "ticks_ready": 160,
                "combined_move": 92.0,
                "higher_win_prob": 0.36,
                "lower_win_prob": 0.53,
                "is_active": False,
            },
            "R_50": {
                "symbol": "R_50",
                "ticks_ready": 90,
                "combined_move": 999.0,
                "higher_win_prob": 0.49,
                "lower_win_prob": 0.41,
                "is_active": False,
            },
        },
    }

    recs = _get_top_unchain_scanner_recs(scanner, limit=4)

    assert [row["symbol"] for row in recs] == ["R_25", "R_10"]
    assert all(int(row["ticks_ready"]) >= 120 for row in recs)
    assert all(1 <= int(row["score"]) <= 99 for row in recs)
