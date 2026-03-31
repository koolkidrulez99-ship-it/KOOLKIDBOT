from collections import deque
from types import SimpleNamespace

import server
from strategies.higher_lower_predictor import predict_higher_lower_percentages


def _tick_times(count, step=1.0, start=1_000.0):
    return [float(start + (idx * step)) for idx in range(count)]


def _rising_prices(count):
    prices = [100.0]
    for idx in range(1, count):
        bump = 0.18 if (idx % 4) else 0.11
        prices.append(round(prices[-1] + bump, 5))
    return prices


def test_predictor_normalizes_and_favors_higher_for_clean_uptrend():
    prices = _rising_prices(80)
    result = predict_higher_lower_percentages(
        market_symbol="R_75",
        duration=5,
        duration_unit="t",
        prices=prices,
        tick_times=_tick_times(len(prices)),
        barrier_value="+0.05",
    )

    assert result["status"] == "success"
    assert result["higher_pct"] > result["lower_pct"]
    assert round(result["higher_pct"] + result["lower_pct"], 1) == 100.0
    assert result["suggested_action"] == "Take Higher"
    assert result["confidence_label"] in {"Strong", "Good", "Weak"}
    assert set(result["score_breakdown"].keys()) == {
        "direction",
        "strength",
        "persistence",
        "simulation",
        "market_quality",
    }


def test_predictor_skips_flat_mixed_market():
    prices = [
        100.00, 100.01, 99.99, 100.00, 100.01, 99.99, 100.00, 100.01,
        99.99, 100.00, 100.01, 99.99, 100.00, 100.01, 99.99, 100.00,
        100.01, 99.99, 100.00, 100.01, 99.99, 100.00, 100.01, 99.99,
    ]
    result = predict_higher_lower_percentages(
        market_symbol="R_25",
        duration=5,
        duration_unit="t",
        prices=prices,
        tick_times=_tick_times(len(prices)),
    )

    assert result["status"] == "success"
    assert round(result["higher_pct"] + result["lower_pct"], 1) == 100.0
    assert result["suggested_action"] == "Skip"
    assert result["confidence_label"] == "Skip"


def test_higher_lower_prediction_route_uses_live_unchain_series(monkeypatch):
    state = {
        "current_symbol": "R_75",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=_rising_prices(90),
                tick_time_history=_tick_times(90),
            )
        },
        "unchain_hl": {
            "duration": 5,
            "duration_unit": "t",
            "higher_barrier": "+0.05",
            "lower_barrier": "-0.05",
        },
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-hl-live", state))

    with server.app.test_client() as client:
        response = client.post(
            "/higher_lower_prediction",
            json={"symbol": "R_75", "duration": 5, "duration_unit": "t", "side": "HIGHER"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["market"] == "R_75"
    assert payload["source"] == "live"
    assert payload["suggested_action"] == "Take Higher"


def test_higher_lower_prediction_route_can_use_scanner_buffer(monkeypatch):
    prices = _rising_prices(70)
    state = {
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(price_history=[], tick_time_history=[])},
        "unchain_hl": {"duration": 5, "duration_unit": "t"},
        "unchain_scanner": {"buffers": {"R_50": deque(prices, maxlen=320)}},
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-hl-scan", state))

    with server.app.test_client() as client:
        response = client.post(
            "/higher_lower_prediction",
            json={"symbol": "R_50", "duration": 5, "duration_unit": "t", "barrier": "+0.03"},
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["market"] == "R_50"
    assert payload["source"] == "scanner"
    assert payload["available_ticks"] == len(prices)
