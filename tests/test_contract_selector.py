from strategies import contract_selector as selector
import server


def test_contract_selector_auto_select_prefers_stronger_valid_model(monkeypatch):
    monkeypatch.setattr(selector, "predict_higher_lower_percentages", lambda **_kwargs: {
        "status": "success",
        "preferred_side": "HIGHER",
        "side_confidence": 72.0,
        "model_confidence": 74.0,
        "model_valid": True,
        "gap": 26.0,
        "reasoning_summary": "Directional edge is clean.",
    })
    monkeypatch.setattr(selector, "predict_touch_no_touch_percentages", lambda **_kwargs: {
        "status": "success",
        "preferred_side": "NO_TOUCH",
        "side_confidence": 69.0,
        "model_confidence": 81.0,
        "model_valid": True,
        "gap": 38.0,
        "reasoning_summary": "Barrier behavior is cleaner.",
    })

    payload = selector.analyze_contract_selector(
        market_symbol="R_10",
        duration=5,
        duration_unit="t",
        prices=[100 + (idx * 0.01) for idx in range(30)],
        tick_times=[idx * 2 for idx in range(30)],
        hl_barrier_value="+0.12",
        tnt_barrier_value="+0.12",
        mode="AUTO_SELECT",
    )

    assert payload["status"] == "success"
    assert payload["chosen_contract_type"] == "TOUCH / NO TOUCH"
    assert payload["chosen_side"] == "NO_TOUCH"
    assert payload["suggested_action"] == "TAKE NO TOUCH"


def test_contract_selector_respects_mode_restriction(monkeypatch):
    monkeypatch.setattr(selector, "predict_higher_lower_percentages", lambda **_kwargs: {
        "status": "success",
        "preferred_side": "LOWER",
        "side_confidence": 66.0,
        "model_confidence": 68.0,
        "model_valid": True,
        "gap": 22.0,
        "reasoning_summary": "Directional edge is valid.",
    })
    monkeypatch.setattr(selector, "predict_touch_no_touch_percentages", lambda **_kwargs: {
        "status": "success",
        "preferred_side": "TOUCH",
        "side_confidence": 78.0,
        "model_confidence": 84.0,
        "model_valid": True,
        "gap": 42.0,
        "reasoning_summary": "Barrier edge is stronger.",
    })

    payload = selector.analyze_contract_selector(
        market_symbol="R_10",
        duration=5,
        duration_unit="t",
        prices=[100 + (idx * 0.01) for idx in range(30)],
        tick_times=[idx * 2 for idx in range(30)],
        hl_barrier_value="+0.12",
        tnt_barrier_value="+0.12",
        mode="HIGHER_LOWER_ONLY",
    )

    assert payload["chosen_contract_type"] == "HIGHER / LOWER"
    assert payload["chosen_side"] == "LOWER"
    assert payload["suggested_action"] == "TAKE LOWER"


def test_contract_selector_skips_when_both_models_are_weak(monkeypatch):
    weak = {
        "status": "success",
        "preferred_side": "HIGHER",
        "side_confidence": 54.0,
        "model_confidence": 49.0,
        "model_valid": False,
        "gap": 6.0,
        "reasoning_summary": "Weak edge.",
    }
    monkeypatch.setattr(selector, "predict_higher_lower_percentages", lambda **_kwargs: dict(weak))
    monkeypatch.setattr(selector, "predict_touch_no_touch_percentages", lambda **_kwargs: dict(weak, preferred_side="NO_TOUCH"))

    payload = selector.analyze_contract_selector(
        market_symbol="R_10",
        duration=5,
        duration_unit="t",
        prices=[100 + (idx * 0.01) for idx in range(30)],
        tick_times=[idx * 2 for idx in range(30)],
        hl_barrier_value="+0.12",
        tnt_barrier_value="+0.12",
        mode="AUTO_SELECT",
    )

    assert payload["chosen_contract_type"] == "SKIP"
    assert payload["suggested_action"] == "SKIP"
    assert payload["trade_valid"] is False


def test_contract_selector_route_uses_profile_defaults(monkeypatch):
    captured = {}
    state = {
        "active_profile": "NTT",
        "current_symbol": "R_10",
        "ntt": {
            "touch_barrier": "+0.17",
            "no_touch_barrier": "+0.17",
            "duration": 5,
            "duration_unit": "t",
            "contract_selector_mode": "AUTO_SELECT",
        },
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-test", state))

    def fake_builder(_state, **kwargs):
        captured.update(kwargs)
        return {"status": "success", "chosen_contract_type": "SKIP", "suggested_action": "SKIP"}

    monkeypatch.setattr(server, "_build_contract_selector_payload", fake_builder)

    with server.app.test_client() as client:
        response = client.post("/contract_selector_analysis", json={"profile": "NTT"})

    assert response.status_code == 200
    assert captured["profile_key"] == "NTT"
    assert captured["tnt_barrier_value"] == "+0.17"
    assert captured["mode"] == "AUTO_SELECT"
