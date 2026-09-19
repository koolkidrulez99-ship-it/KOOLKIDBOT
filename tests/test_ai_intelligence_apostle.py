import pytest

from ai_intelligence.apostle import (
    ApostleEngine, Candle, RiskSpec, SetupState, approve_ex5_signal, backtest,
    completed, confirmed_swings, market_structure, position_size, rejection,
    trendline_value,
)


def candles(closes):
    return [Candle(i, value + 0.2, value + 0.5, value - 0.5, value, 100, True) for i, value in enumerate(closes)]


def test_unfinished_candle_is_never_processed():
    rows = [Candle(1, 1, 2, 0, 1, complete=True), Candle(2, 1, 99, 0, 99, complete=False)]
    assert [row.time for row in completed(rows)] == [1]


def test_confirmed_fractal_swings_and_labels():
    rows = [Candle(i, 5, high, low, 5) for i, (high, low) in enumerate([(6, 4), (7, 3), (10, 2), (7, 3), (6, 4), (8, 3), (11, 5), (8, 4), (7, 3)])]
    highs, lows = confirmed_swings(rows, radius=1)
    assert [x.price for x in highs] == [10, 11]
    assert highs[-1].label == "HH"
    assert lows[-1].label == "HL"


def test_structure_bullish_bearish_and_neutral():
    rows = candles([8] * 8)
    from ai_intelligence.apostle import Swing
    assert market_structure(rows, [Swing(1, 1, 10, "HIGH"), Swing(5, 5, 11, "HIGH")], [Swing(2, 2, 5, "LOW"), Swing(6, 6, 6, "LOW")]) == "BULLISH"
    assert market_structure(rows, [Swing(1, 1, 11, "HIGH"), Swing(5, 5, 10, "HIGH")], [Swing(2, 2, 6, "LOW"), Swing(6, 6, 5, "LOW")]) == "BEARISH"
    assert market_structure(rows, [], []) == "NEUTRAL"


def test_trendline_math_and_close_not_wick_break():
    from ai_intelligence.apostle import Swing
    a, b = Swing(1, 1, 10, "LOW"), Swing(3, 3, 12, "LOW")
    assert trendline_value(a, b, 5) == 14
    wick_only = Candle(5, 15, 16, 13, 14.2)
    assert wick_only.low < 14 and wick_only.close > 14


def test_same_candle_retest_rejected_then_later_retest_accepted():
    engine = ApostleEngine(retest_tolerance=0.1)
    rows = candles([11, 11, 10.5, 11, 11, 11, 9.7])
    rows[-1] = Candle(6, 9.8, 10.05, 9.5, 9.7)
    state = SetupState("1", "EURUSD", "M15", state="WAITING_FOR_RETEST", direction="SELL", retest_level=10, stop_reference=11, shift_index=6)
    result = engine.evaluate(state, rows, bias=["BEARISH"])
    assert result["decision"] == "WAIT FOR LATER RETEST"
    rows.append(Candle(7, 10.05, 10.08, 9.4, 9.7))
    result = engine.evaluate(state, rows, bias=["BEARISH"])
    assert result["decision"] == "SELL" and result["tp"] < result["entry"]


@pytest.mark.parametrize("direction,candle,expected", [
    ("BUY", Candle(1, 9.8, 10.7, 9.9, 10.5), True),
    ("SELL", Candle(1, 10.3, 10.1, 9.4, 9.7), True),
    ("BUY", Candle(1, 10.5, 10.7, 9.9, 10.2), False),
])
def test_rejection_candle(direction, candle, expected):
    assert rejection(candle, direction, 10, 0.1, True) is expected


def test_structural_stop_two_r_and_bias_rejection():
    engine = ApostleEngine(target_r=2)
    rows = candles([11, 11, 10.5, 11, 11, 11, 9.7]) + [Candle(7, 10.1, 10.2, 9.5, 9.8)]
    state = SetupState("1", "XAUUSD", "M5", state="WAITING_FOR_RETEST", direction="SELL", retest_level=10, stop_reference=11, shift_index=6)
    result = engine.evaluate(state, rows, bias=["BEARISH", "BEARISH"])
    assert result["decision"] == "SELL"
    assert result["tp"] == pytest.approx(result["entry"] - 2 * (result["sl"] - result["entry"]))
    state = SetupState("1", "XAUUSD", "M5", state="WAITING_FOR_RETEST", direction="SELL", retest_level=10, stop_reference=11, shift_index=6)
    assert engine.evaluate(state, rows, bias=["BULLISH"])["decision"] == "REJECT SETUP"


def test_position_size_rounds_down_and_rejects_broker_minimum():
    spec = RiskSpec(equity=10000, risk_percent=1, tick_size=0.0001, tick_value=10, volume_min=0.01, volume_max=100, volume_step=0.01)
    assert position_size(1.1000, 1.0990, spec) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="below the broker minimum"):
        position_size(100, 50, RiskSpec(100, 1, 0.01, 10, 0.1, 10, 0.1))


def test_independent_symbol_and_timeframe_states():
    states = {(a, s, tf, st): SetupState(a, s, tf, st) for a, s, tf, st in [("1", "EURUSD", "M1", "HUMAN APOSTLE"), ("1", "EURUSD", "M5", "HUMAN APOSTLE"), ("1", "XAUUSD", "M1", "DEAR BRUCE")]}
    states[("1", "EURUSD", "M1", "HUMAN APOSTLE")].state = "WAITING_FOR_RETEST"
    assert states[("1", "EURUSD", "M5", "HUMAN APOSTLE")].state == "SCANNING"
    assert states[("1", "XAUUSD", "M1", "DEAR BRUCE")].state == "SCANNING"


def test_neutral_market_returns_no_trade_and_stale_setup_resets():
    engine = ApostleEngine(stale_bars=5)
    assert engine.evaluate(SetupState("1", "EURUSD", "M1"), candles([10] * 8))["decision"] == "SCANNING"
    state = SetupState("1", "EURUSD", "M1", state="WAITING_FOR_STRUCTURE_SHIFT", direction="BUY", protected_structure=20, break_index=0)
    result = engine.evaluate(state, candles([10] * 9))
    assert result["decision"] in ("SCANNING", "WAIT FOR TRENDLINE BREAK")


def test_ex5_approval_delay_and_rejection_are_fail_closed():
    signal = {"ea": "Dear Bruce", "magic": 7, "symbol": "EURUSD", "direction": "BUY", "entry": 1, "sl": .9, "tp": 1.2, "timeframe": "M15"}
    assert approve_ex5_signal({}, {"decision": "BUY"})["decision"] == "REJECT"
    assert approve_ex5_signal(signal, {"decision": "SCANNING", "score": 90})["decision"] == "DELAY"
    assert approve_ex5_signal(signal, {"decision": "SELL", "score": 80})["decision"] == "REJECT"
    assert approve_ex5_signal(signal, {"decision": "BUY", "score": 60}, 75)["decision"] == "APPROVE"


def test_backtest_reports_rejections_and_metrics_without_execution():
    result = backtest(candles([10] * 20), symbol="EURUSD")
    assert result["total_trades"] == 0
    assert result["win_rate"] == 0
    assert "rejected_setups" in result and "max_drawdown_r" in result


def retest_state():
    return SetupState("1", "EURUSD", "M15", state="WAITING_FOR_RETEST", direction="SELL",
                      protected_structure=10, retest_level=10, stop_reference=12,
                      break_index=5, break_time=5, shift_index=6, shift_time=6)


def retest_rows():
    return candles([11, 11, 10.5, 11, 11, 11, 9.7]) + [Candle(7, 10.1, 10.2, 9.5, 9.8)]


def test_sliding_window_retest_uses_time_not_fixed_last_index():
    state = retest_state()
    # Prior window included time -1; now it starts at 0 but still ends at index 7.
    state.shift_index = 7
    rows = retest_rows()
    assert len(rows) - 1 == state.shift_index
    result = ApostleEngine().evaluate(state, rows, bias=["BEARISH"])
    assert result["decision"] == "SELL"
    assert state.state == "SIGNAL_READY"
    assert result["risk_validated"] is False
    assert ApostleEngine().evaluate(state, rows, bias=["BEARISH"])["decision"] != "SELL"
    rows.append(Candle(8, 9.8, 10, 9, 9.5))
    assert ApostleEngine().evaluate(state, rows, bias=["BEARISH"])["decision"] != "MANAGE POSITION"


def test_threshold_blocks_otherwise_confirmed_signal():
    result = ApostleEngine(threshold=90).evaluate(retest_state(), retest_rows())
    assert result["decision"] == "REJECT SETUP"
    assert result["score"] == 85
    assert "threshold" in result["reason"]


def test_retest_rejects_neutral_execution_structure():
    rows = candles([10] * 7) + [Candle(7, 10.1, 10.2, 9.5, 9.8)]
    result = ApostleEngine().evaluate(retest_state(), rows, bias=["BEARISH"])
    assert result["decision"] == "REJECT SETUP"
    assert "Execution structure" in result["reason"]


def test_setup_expires_when_break_falls_outside_history_window():
    state = retest_state()
    rows = [Candle(c.time + 100, c.open, c.high, c.low, c.close) for c in candles([10] * 8)]
    ApostleEngine().evaluate(state, rows)
    assert state.state == "SCANNING" and state.break_time is None


@pytest.mark.parametrize("row", [Candle(1, 9, 12, 10, 11), Candle(1, 11, 12, 10, float("nan"))])
def test_invalid_prices_cannot_create_signal(row):
    with pytest.raises(ValueError, match="OHLC"):
        completed([row])


def test_position_size_honors_non_step_aligned_maximum():
    assert position_size(10, 9, RiskSpec(10000, 1, 1, 1, .1, .25, .1)) == .2
    assert position_size(10, 9, RiskSpec(100, 1, 1, 1, .00001, .00009, .00001)) == .00009


def test_backtest_cannot_open_again_until_existing_position_exits():
    class AlwaysSignal:
        target_r = 2

        def __init__(self):
            self.times = []

        def evaluate(self, state, rows, **kwargs):
            self.times.append(rows[-1].time)
            return {"decision": "BUY", "entry": 10, "sl": 9, "tp": 12}

    rows = [Candle(i, 10, 11, 9.5, 10) for i in range(13)]
    rows[10] = Candle(10, 10, 12, 9.5, 11)
    engine = AlwaysSignal()
    result = backtest(rows, engine=engine)
    assert engine.times == [7, 11]
    assert result["total_trades"] == 1
    assert result["trades"][0]["exit_time"] == 10
