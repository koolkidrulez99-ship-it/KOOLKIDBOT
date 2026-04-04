from strategies.touch_no_touch_predictor import predict_touch_no_touch_percentages


def test_touch_no_touch_predictor_normalizes_percentages():
    prices = [100.0 + (idx * 0.03) for idx in range(30)]
    tick_times = [idx * 2 for idx in range(30)]

    payload = predict_touch_no_touch_percentages(
        market_symbol="R_10",
        duration=5,
        duration_unit="t",
        prices=prices,
        tick_times=tick_times,
        barrier_value="+0.12",
    )

    assert payload["status"] == "success"
    total = round(float(payload["touch_pct"]) + float(payload["no_touch_pct"]), 1)
    assert total == 100.0
    assert payload["preferred_side"] in ("TOUCH", "NO_TOUCH")
    assert "model_confidence" in payload


def test_touch_no_touch_predictor_requires_history():
    payload = predict_touch_no_touch_percentages(
        market_symbol="R_10",
        duration=5,
        duration_unit="t",
        prices=[100.0, 100.02, 100.01],
        tick_times=[0, 2, 4],
        barrier_value="+0.12",
    )

    assert payload["status"] == "error"
