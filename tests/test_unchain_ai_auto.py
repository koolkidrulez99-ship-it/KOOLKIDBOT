import server


def test_unchain_ai_auto_defaults_are_looser():
    u = server._ensure_unchain_hl_state({})

    assert u["auto_start_threshold"] == 48.0
    assert u["auto_min_movement"] == 0.06
    assert u["auto_min_tick_speed"] == 2.4
    assert u["auto_min_range"] == 0.12


def test_ai_auto_trade_uses_saved_barriers_when_dynamic_setup_missing(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "unchain_hl": {
            "ai_auto_trade_enabled": True,
            "higher_stake": 1.0,
            "lower_stake": 1.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
        "strategies": {"UNCHAIN": object()},
    }
    placed = []

    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "confidence_score": 55.0,
            "market_confidence": 55.0,
            "breakout_ready": True,
            "reject_reasons": [],
            "dynamic_allowed": False,
            "dynamic_duration": None,
            "dynamic_duration_unit": "t",
            "dynamic_higher_barrier": None,
            "dynamic_lower_barrier": None,
        },
    )
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_ai_auto_trade("cid", state) is True
    assert len(placed) == 2
    assert placed[0]["barrier"] == "+0.12"
    assert placed[1]["barrier"] == "-0.12"
    assert placed[0]["duration"] == 5


def test_ai_auto_gate_triggers_on_confidence_and_breakout_even_with_old_diagnostic_reasons(monkeypatch):
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "confidence_score": 55.0,
            "market_confidence": 55.0,
            "breakout_ready": True,
            "reject_reasons": ["Compression high (diagnostic only)"],
            "movement_score": 0,
            "volatility_score": 0,
            "range_score": 0,
            "trap_zone_score": 0,
        },
    )

    gate = server._get_unchain_auto_gate({}, {"auto_start_threshold": 48.0})

    assert gate["ready"] is True
    assert gate["breakout_ready"] is True
    assert gate["reject_reasons"] == []


def test_ai_auto_gate_waits_for_breakout_after_confidence(monkeypatch):
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "confidence_score": 62.0,
            "market_confidence": 62.0,
            "breakout_ready": False,
            "reject_reasons": [],
            "movement_score": 0,
            "volatility_score": 0,
            "range_score": 0,
            "trap_zone_score": 0,
        },
    )

    gate = server._get_unchain_auto_gate({}, {"auto_start_threshold": 48.0})

    assert gate["ready"] is False
    assert gate["breakout_ready"] is False
    assert gate["reject_reasons"] == ["waiting for breakout"]
