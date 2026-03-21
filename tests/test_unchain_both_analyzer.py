from types import SimpleNamespace

import server


def _make_state(count=140):
    prices = [100.0 + idx for idx in range(count)]
    times = [1_700_000_000.0 + idx for idx in range(count)]
    return {
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=prices,
                tick_time_history=times,
            )
        },
        "unchain_hl": {
            "higher_stake": 50.0,
            "lower_stake": 50.0,
        },
    }


def test_unchain_duration_sanitizer_allows_three_tick_setups():
    assert server._sanitize_unchain_duration(3, "t") == 3


def test_both_analyzer_starts_after_fifty_ticks():
    analysis = server._run_unchain_both_analyzer(_make_state(count=49))

    assert analysis["required_min_ticks"] == 50
    assert analysis["status"] == "WAIT"
    assert "49/50" in analysis["reason"]


def test_both_analyzer_keeps_appliable_recommendation_even_when_waiting(monkeypatch):
    def fake_quote(state, *, side, stake, symbol, barrier, duration, duration_unit="t", timeout_sec=1.6):
        return {
            "ask_price": float(stake),
            "payout": float(stake) + 60.0,
            "barrier": str(barrier),
        }, None

    prices = [100.0 + (0.0005 if idx % 2 else 0.0) for idx in range(120)]
    times = [1_700_000_000.0 + idx for idx in range(120)]
    state = {
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=prices,
                tick_time_history=times,
            )
        },
        "unchain_hl": {
            "higher_stake": 50.0,
            "lower_stake": 50.0,
        },
    }
    monkeypatch.setattr(server, "_request_unchain_proposal_quote", fake_quote)

    analysis = server._run_unchain_both_analyzer(state)

    assert analysis["status"] == "WAIT"
    assert analysis["recommended"] is not None
    assert analysis["recommended_side"] in {"HIGHER", "LOWER", "BOTH"}
    assert analysis["recommended"]["is_trade_ready"] is False


def _fake_quote_factory(case):
    def _fake_quote(state, *, side, stake, symbol, barrier, duration, duration_unit="t", timeout_sec=1.6):
        if abs(float(barrier)) > 0.10:
            return None, "Barrier is out of acceptable range"
        payout = (case.get(int(duration)) or {}).get(str(side).upper())
        if payout is None:
            return None, "No quote"
        return {
            "ask_price": float(stake),
            "payout": float(payout),
            "barrier": str(barrier),
        }, None

    return _fake_quote


def test_both_analyzer_falls_back_to_best_higher_when_both_profit_floor_fails(monkeypatch):
    monkeypatch.setattr(
        server,
        "_request_unchain_proposal_quote",
        _fake_quote_factory(
            {
                3: {"HIGHER": 152.0, "LOWER": 140.0},
                5: {"HIGHER": 160.0, "LOWER": 145.0},
                8: {"HIGHER": 151.0, "LOWER": 140.0},
                10: {"HIGHER": 149.0, "LOWER": 139.0},
            }
        ),
    )

    analysis = server._run_unchain_both_analyzer(_make_state())

    assert analysis["status"] == "READY"
    assert analysis["recommended_side"] == "HIGHER"
    assert analysis["signal"] == "BEST HIGHER"
    assert analysis["both_profit_target"] == 50.0
    assert analysis["both_min_win_profit"] < analysis["both_profit_target"]
    assert analysis["market_outlook"] == "HIGHER"
    assert analysis["higher_expected_profit"] > analysis["lower_expected_profit"]


def test_both_analyzer_only_recommends_both_when_each_side_clears_profit_floor(monkeypatch):
    monkeypatch.setattr(
        server,
        "_request_unchain_proposal_quote",
        _fake_quote_factory(
            {
                3: {"HIGHER": 149.0, "LOWER": 148.0},
                5: {"HIGHER": 160.0, "LOWER": 158.0},
                8: {"HIGHER": 149.0, "LOWER": 149.0},
                10: {"HIGHER": 148.0, "LOWER": 149.0},
            }
        ),
    )

    analysis = server._run_unchain_both_analyzer(_make_state())

    assert analysis["status"] == "READY"
    assert analysis["recommended_side"] == "BOTH"
    assert analysis["signal"] == "BEST BOTH"
    assert analysis["recommended_duration"] == 5
    assert analysis["both_profit_target"] == 50.0
    assert analysis["both_min_win_profit"] >= analysis["both_profit_target"]
    assert analysis["best_both_setup"]["higher_barrier"].startswith("+")
    assert analysis["best_both_setup"]["lower_barrier"].startswith("-")
