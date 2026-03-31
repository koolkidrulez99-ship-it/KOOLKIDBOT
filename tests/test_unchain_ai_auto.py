import server
import pytest
from types import SimpleNamespace
from flask import json


def test_unchain_ai_auto_defaults_are_looser():
    u = server._ensure_unchain_hl_state({})

    assert u["auto_start_threshold"] == 48.0
    assert u["auto_min_movement"] == 0.06
    assert u["auto_min_tick_speed"] == 2.4
    assert u["auto_min_range"] == 0.12


def test_finalize_unchain_contract_forgets_open_contract_subscription():
    sent = []

    class FakeWS:
        def send(self, payload):
            sent.append(json.loads(payload))

    state = {
        "ws_connected": True,
        "ws": FakeWS(),
        "current_symbol": "R_25",
        "open_contract_subs": {"123": "sub-123"},
        "unchain_hl": {
            "active_contracts": {
                "123": {
                    "contract_id": "123",
                    "type": "HIGHER",
                    "stake": 5.0,
                    "symbol": "R_25",
                    "time": "12:00:00",
                    "duration": 5,
                    "duration_unit": "t",
                }
            },
            "stats": {"wins": 0, "losses": 0, "net_pnl": 0.0},
        },
    }

    entry = server._finalize_unchain_contract(
        state,
        {"contract_id": "123", "profit": 1.5},
        meta={"type": "HIGHER", "stake": 5.0, "symbol": "R_25", "time": "12:00:00"},
    )

    assert entry["result"] == "WIN"
    assert state["open_contract_subs"] == {}
    assert sent == [{"forget": "sub-123"}]


def test_ai_auto_trade_uses_saved_barriers_when_dynamic_setup_missing(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 10.0,
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


def test_koolkid_hl_starts_simulation_on_weaker_side(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_sim_duration": 15,
            "koolkid_live_duration": 5,
            "koolkid_hl_loss_trigger_pct": 50,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["side"] == "HIGHER"
    assert sim["opposite_side"] == "LOWER"
    assert sim["simulation_duration"] == 15
    assert sim["live_duration"] == 5
    assert sim["check_at"] == pytest.approx(sim["started_at"] + 7.0)
    assert sim["loss_trigger_pct"] == 50
    assert sim["sim_barrier"] == "+0.12"
    assert sim["live_barrier"] == "-0.06"


def test_koolkid_hl_can_force_higher_side_simulation(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "koolkid_hl_sim_side": "HIGHER",
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_higher_barrier": "+0.09",
            "koolkid_lower_barrier": "-0.22",
            "koolkid_hl_loss_trigger_pct": 50,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 65.0, "lower_pct": 35.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["side"] == "HIGHER"
    assert sim["opposite_side"] == "LOWER"
    assert sim["sim_barrier"] == "+0.12"
    assert sim["live_barrier"] == "-0.22"


def test_koolkid_hl_can_force_lower_side_simulation(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "koolkid_hl_sim_side": "LOWER",
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_higher_barrier": "+0.09",
            "koolkid_lower_barrier": "-0.22",
            "koolkid_hl_loss_trigger_pct": 50,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["side"] == "LOWER"
    assert sim["opposite_side"] == "HIGHER"
    assert sim["sim_barrier"] == "-0.12"
    assert sim["live_barrier"] == "+0.09"


def test_koolkid_hl_uses_saved_real_side_barrier(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_higher_barrier": "+0.09",
            "koolkid_lower_barrier": "-0.22",
            "koolkid_hl_loss_trigger_pct": 50,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["side"] == "HIGHER"
    assert sim["opposite_side"] == "LOWER"
    assert sim["live_barrier"] == "-0.22"


def test_koolkid_live_barrier_respects_koolkid_half_toggle():
    u = {
        "koolkid_higher_barrier": "+0.20",
        "koolkid_lower_barrier": "-0.30",
        "koolkid_half_barrier_enabled": True,
    }

    assert float(server._get_unchain_koolkid_live_barrier(u, "HIGHER", "t")) == pytest.approx(0.10)
    assert float(server._get_unchain_koolkid_live_barrier(u, "LOWER", "t")) == pytest.approx(-0.15)


def test_koolkid_hl_supports_tick_sim_and_minute_live_units(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0, tick_count=120)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_sim_duration": 6,
            "koolkid_sim_duration_unit": "t",
            "koolkid_live_duration": 2,
            "koolkid_live_duration_unit": "m",
            "koolkid_hl_loss_trigger_pct": 50,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["simulation_duration_unit"] == "t"
    assert sim["live_duration_unit"] == "m"
    assert sim["started_tick"] == 120
    assert sim["check_tick"] == 123
    assert sim["end_tick"] == 126

def test_koolkid_hl_uses_8_second_check_for_60pct_on_15_second_sim(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_sim_duration": 15,
            "koolkid_live_duration": 5,
            "koolkid_hl_loss_trigger_pct": 60,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["loss_trigger_pct"] == 60
    assert sim["check_at"] == pytest.approx(sim["started_at"] + 8.0)


def test_koolkid_hl_uses_9_second_check_for_70pct_on_20_second_sim(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_sim_duration": 20,
            "koolkid_live_duration": 5,
            "koolkid_hl_loss_trigger_pct": 70,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_get_unchain_bias_payload",
        lambda state, u=None: {"higher_pct": 35.0, "lower_pct": 65.0},
    )
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.02,
            "current_20_range": 0.18,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_hl("cid", state) is False
    sim = state["unchain_hl"]["koolkid_hl_simulation"]

    assert sim is not None
    assert sim["loss_trigger_pct"] == 70
    assert sim["check_at"] == pytest.approx(sim["started_at"] + 9.0)


def test_koolkid_hl_places_opposite_trade_after_losing_simulation(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=99.7,
                price_history=[100.5, 100.4, 100.2, 100.0, 99.9, 99.8, 99.7],
            )
        },
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_hl_simulation": {
                "active": True,
                "side": "HIGHER",
                "opposite_side": "LOWER",
                "symbol": "R_25",
                "stake": 10.0,
                "sim_barrier": "+0.12",
                "sim_barrier_mag": 0.12,
                "live_barrier": "-0.06",
                "live_barrier_mag": 0.06,
                "start_price": 100.0,
                "current_price": 99.7,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "loss_trigger_pct": 50,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-HL-SIM",
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.42,
            "compression_score": 30.0,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_hl("cid", state) is True
    assert len(placed) == 1
    assert placed[0]["side"] == "LOWER"
    assert placed[0]["barrier"] == "-0.06"
    assert placed[0]["duration"] == 5


def test_unchain_trade_route_persists_form_values_and_sends_both(monkeypatch):
    cid = "manual-both-route"
    state = {
        "active_profile": "UNCHAIN",
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "unchain_hl": {
            "higher_stake": 1.0,
            "lower_stake": 1.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: (cid, state))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server.time, "sleep", lambda *_args, **_kwargs: None)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    with server.app.test_request_context(
        "/unchain_trade",
        method="POST",
        data=json.dumps({
            "side": "BOTH",
            "higher_stake": 3.5,
            "lower_stake": 4.5,
            "higher_barrier": "+0.44",
            "lower_barrier": "-0.55",
            "duration": 8,
            "duration_unit": "t",
        }),
        content_type="application/json",
    ):
        response = server.unchain_trade_route()

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["placed"] == ["HIGHER", "LOWER"]
    assert state["unchain_hl"]["higher_stake"] == 3.5
    assert state["unchain_hl"]["lower_stake"] == 4.5
    assert state["unchain_hl"]["higher_barrier"] == "+0.44"
    assert state["unchain_hl"]["lower_barrier"] == "-0.55"
    assert state["unchain_hl"]["duration"] == 8
    assert len(placed) == 2
    assert placed[0]["barrier"] == "+0.44"
    assert placed[1]["barrier"] == "-0.55"
    assert state["unchain_hl"]["koolkid_hl_simulation"] is None


def test_koolkid_hl_uses_selected_live_duration_unit_when_firing(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=99.7,
                price_history=[100.5, 100.4, 100.2, 100.0, 99.9, 99.8, 99.7],
            )
        },
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_hl_simulation": {
                "active": True,
                "side": "HIGHER",
                "opposite_side": "LOWER",
                "symbol": "R_25",
                "stake": 10.0,
                "sim_barrier": "+0.12",
                "sim_barrier_mag": 0.12,
                "live_barrier": "-0.06",
                "live_barrier_mag": 0.06,
                "start_price": 100.0,
                "current_price": 99.7,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "simulation_duration_unit": "s",
                "live_duration": 2,
                "live_duration_unit": "m",
                "loss_trigger_pct": 50,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-HL-SIM",
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.42,
            "compression_score": 30.0,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_hl("cid", state) is True
    assert len(placed) == 1
    assert placed[0]["duration"] == 2
    assert placed[0]["duration_unit"] == "m"

def test_koolkid_hl_60pct_trigger_waits_if_sim_not_losing_enough(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=99.8,
                price_history=[100.5, 100.4, 100.2, 100.0, 99.95, 99.9, 99.8],
            )
        },
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_hl_simulation": {
                "active": True,
                "side": "HIGHER",
                "opposite_side": "LOWER",
                "symbol": "R_25",
                "stake": 10.0,
                "sim_barrier": "+0.12",
                "sim_barrier_mag": 0.12,
                "live_barrier": "-0.06",
                "live_barrier_mag": 0.06,
                "start_price": 100.0,
                "current_price": 99.8,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "loss_trigger_pct": 60,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-HL-SIM",
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.42,
            "compression_score": 30.0,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)
    monkeypatch.setattr(server, "_estimate_unchain_koolkid_hl_value", lambda sim, current_price, metrics, max_balance_ratio=1.35: (4.5, -5.5, 0.45))

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_hl("cid", state) is False
    assert placed == []
    assert state["unchain_hl"]["koolkid_hl_simulation"] is None
    assert "60% loss trigger" in state["unchain_hl"]["koolkid_hl_last_reason"]


def test_koolkid_hl_skips_when_old_safety_checks_fail(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=99.7,
                price_history=[100.0, 99.99, 100.0, 99.99, 100.0, 99.98, 99.7],
            )
        },
        "unchain_hl": {
            "koolkid_hl_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_hl_simulation": {
                "active": True,
                "side": "HIGHER",
                "opposite_side": "LOWER",
                "symbol": "R_25",
                "stake": 10.0,
                "sim_barrier": "+0.12",
                "sim_barrier_mag": 0.12,
                "live_barrier": "-0.40",
                "live_barrier_mag": 0.40,
                "start_price": 100.0,
                "current_price": 99.7,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "loss_trigger_pct": 50,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-HL-SIM",
            },
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.01,
            "current_20_range": 0.08,
            "compression_score": 95.0,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    placed = []

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_hl("cid", state) is False
    assert placed == []
    assert state["unchain_hl"]["koolkid_hl_simulation"] is None


def test_check_unchain_pair_balance_blocks_when_total_stake_exceeds_balance():
    ok, msg, normalized, total, balance = server._check_unchain_pair_balance(
        {"balance": 9.0},
        [("HIGHER", 5.0, "+0.12"), ("LOWER", 5.0, "-0.12")],
        failure_prefix="Trade failed",
    )

    assert ok is False
    assert "need $10.00 total balance for both trades" in msg
    assert normalized[0][0] == "HIGHER"
    assert total == 10.0
    assert balance == 9.0


def test_auto_both_skips_when_balance_cannot_cover_pair(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 5.0,
        "current_symbol": "R_25",
        "unchain_hl": {
            "auto_both_enabled": True,
            "higher_stake": 4.0,
            "lower_stake": 4.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(server, "_send_unchain_hl_trade", lambda client_id, **kwargs: placed.append(kwargs) or (True, "ok"))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    assert server._run_unchain_auto_both("cid", state) is False
    assert placed == []
    assert "need $8.00 total balance for both trades" in state["unchain_hl"]["last_action"]


def test_auto_both_waits_for_ready_both_analysis(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "unchain_hl": {
            "auto_both_enabled": True,
            "higher_stake": 4.0,
            "lower_stake": 4.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_run_unchain_both_analyzer",
        lambda state: {
            "status": "WAIT",
            "reason": "WAIT: no setup passed all barrier analyzer checks.",
        },
    )
    monkeypatch.setattr(server, "_send_unchain_hl_trade", lambda client_id, **kwargs: placed.append(kwargs) or (True, "ok"))

    assert server._run_unchain_auto_both("cid", state) is False
    assert placed == []
    assert "AUTO BOTH waiting" in state["unchain_hl"]["last_action"]


def test_auto_both_uses_ready_both_recommended_setup(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "unchain_hl": {
            "auto_both_enabled": True,
            "higher_stake": 4.0,
            "lower_stake": 4.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_run_unchain_both_analyzer",
        lambda state: {
            "status": "READY",
            "reason": "READY: BEST BOTH",
            "recommended": {
                "recommended_side": "BOTH",
                "is_trade_ready": True,
                "duration": 8,
                "duration_unit": "t",
                "higher_barrier": "+0.21",
                "lower_barrier": "-0.19",
            },
        },
    )
    monkeypatch.setattr(server, "_send_unchain_hl_trade", lambda client_id, **kwargs: placed.append(kwargs) or (True, "ok"))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    assert server._run_unchain_auto_both("cid", state) is True
    assert [call["side"] for call in placed] == ["HIGHER", "LOWER"]
    assert all(call["duration"] == 8 for call in placed)
    assert placed[0]["barrier"] == "+0.21"
    assert placed[1]["barrier"] == "-0.19"


def test_unchain_settings_duration_change_does_not_refresh_barriers(monkeypatch):
    cid = "unchain-settings-no-refresh"
    state = {
        "active_profile": "UNCHAIN",
        "current_symbol": "R_75",
        "ws_connected": True,
        "ws": object(),
        "strategies": {"UNCHAIN": SimpleNamespace()},
        "unchain_hl": {
            "higher_barrier": "+0.33",
            "lower_barrier": "-0.44",
            "duration": 5,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: (cid, state))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "send_stats_update", lambda *args, **kwargs: None)

    with server.app.test_request_context(
        "/unchain_settings",
        method="POST",
        data=json.dumps({"duration_unit": "s", "duration": 15}),
        content_type="application/json",
    ):
        response = server.unchain_settings_route()
        payload = response.get_json()

    assert payload["unchain"]["duration_unit"] == "s"
    assert payload["unchain"]["duration"] == 15
    assert payload["unchain"]["higher_barrier"] == "+0.33"
    assert payload["unchain"]["lower_barrier"] == "-0.44"


def test_unchain_status_route_does_not_auto_refresh_barriers(monkeypatch):
    cid = "unchain-status-no-refresh"
    state = {
        "current_symbol": "R_75",
        "unchain_hl": {
            "higher_barrier": "+0.33",
            "lower_barrier": "-0.44",
        },
    }
    calls = []

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: (cid, state))
    monkeypatch.setattr(server, "_ensure_tick_subscription", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_sync_unchain_market_default_barriers", lambda *args, **kwargs: calls.append(True))

    with server.app.test_request_context("/unchain_status", method="GET"):
        response = server.unchain_status_route()
        payload = response.get_json()

    assert response.status_code == 200
    assert calls == []
    assert payload["unchain"]["higher_barrier"] == "+0.33"
    assert payload["unchain"]["lower_barrier"] == "-0.44"


def test_handle_on_close_schedules_reconnect_only_for_unexpected_close(monkeypatch):
    client_id = "ws-reconnect-test"
    state = server._build_default_client_state()
    state["api_token"] = "token"
    state["ws_nonce"] = 3
    state["balance"] = 25.0
    server.clients[client_id] = state
    calls = []

    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=2.0: calls.append((cid, nonce, delay_sec)) or True)

    server.handle_on_close(client_id, None, 1006, "closed", 3)
    assert calls == [(client_id, 3, 2.0)]

    calls.clear()
    state["ws_stop_event"].set()
    server.handle_on_close(client_id, None, 1000, "manual", 3)
    assert calls == []

    server.clients.pop(client_id, None)


def test_ai_auto_trade_skips_when_balance_cannot_cover_pair(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 6.0,
        "current_symbol": "R_25",
        "unchain_hl": {
            "ai_auto_trade_enabled": True,
            "higher_stake": 4.0,
            "lower_stake": 4.0,
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
            "confidence_score": 60.0,
            "market_confidence": 60.0,
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
    monkeypatch.setattr(server, "_send_unchain_hl_trade", lambda client_id, **kwargs: placed.append(kwargs) or (True, "ok"))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    assert server._run_unchain_ai_auto_trade("cid", state) is False
    assert placed == []
    assert "need $8.00 total balance for both trades" in state["unchain_hl"]["last_action"]


def test_koolkid_both_starts_dual_simulation(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {"UNCHAIN": SimpleNamespace(last_price=100.0)},
        "unchain_hl": {
            "koolkid_both_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_higher_barrier": "+0.10",
            "koolkid_lower_barrier": "-0.14",
            "koolkid_sim_duration": 15,
            "koolkid_live_duration": 5,
        },
    }
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.03,
            "current_20_range": 0.24,
            "compression_score": 35.0,
        },
    )

    assert server._run_unchain_koolkid_both("cid", state) is False
    sim = state["unchain_hl"]["koolkid_both_simulation"]

    assert sim is not None
    assert sim["simulation_duration"] == 15
    assert sim["live_duration"] == 5
    assert sim["check_at"] == pytest.approx(sim["started_at"] + 8.0)
    assert len(sim["sides"]) == 2
    assert {row["side"] for row in sim["sides"]} == {"HIGHER", "LOWER"}


def test_koolkid_both_uses_saved_barriers_on_strong_movement(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=100.20,
                price_history=[99.90, 99.95, 100.00, 100.04, 100.08, 100.12, 100.16, 100.20],
            )
        },
        "unchain_hl": {
            "koolkid_both_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_higher_barrier": "+0.10",
            "koolkid_lower_barrier": "-0.14",
            "koolkid_both_simulation": {
                "active": True,
                "symbol": "R_25",
                "start_price": 100.0,
                "current_price": 100.20,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-BOTH-SIM",
                "sides": [
                    {
                        "side": "HIGHER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "+0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-HIGHER",
                    },
                    {
                        "side": "LOWER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "-0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-LOWER",
                    },
                ],
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.42,
            "compression_score": 30.0,
            "momentum_burst_score": 70.0,
            "micro_breakout_score": 60.0,
            "average_tick_interval": 1.4,
            "min_tick_speed": 2.4,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_both("cid", state) is True
    assert len(placed) == 2
    assert placed[0]["barrier"] == "+0.1"
    assert placed[1]["barrier"] == "-0.14"
    assert placed[0]["stake"] == 10.0
    assert placed[1]["stake"] == 10.0
    assert all(call["respect_half_barrier_toggle"] is False for call in placed)
    assert state["unchain_hl"]["koolkid_both_simulation"] is None


def test_koolkid_both_uses_progress_to_pass_40pct_gate(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=100.20,
                price_history=[99.90, 99.95, 100.00, 100.04, 100.08, 100.12, 100.16, 100.20],
            )
        },
        "unchain_hl": {
            "koolkid_both_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_higher_barrier": "+0.10",
            "koolkid_lower_barrier": "-0.14",
            "koolkid_both_simulation": {
                "active": True,
                "symbol": "R_25",
                "start_price": 100.0,
                "current_price": 100.20,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-BOTH-SIM",
                "sides": [
                    {
                        "side": "HIGHER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "+0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-HIGHER",
                    },
                    {
                        "side": "LOWER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "-0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-LOWER",
                    },
                ],
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.42,
            "compression_score": 30.0,
            "momentum_burst_score": 70.0,
            "micro_breakout_score": 60.0,
            "average_tick_interval": 1.4,
            "min_tick_speed": 2.4,
        },
    )
    monkeypatch.setattr(server, "_estimate_unchain_koolkid_hl_value", lambda sim, current_price, metrics, max_balance_ratio=1.35: (11.0, 1.0, 1.10))
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_both("cid", state) is True
    assert len(placed) == 2
    assert state["unchain_hl"]["koolkid_both_simulation"] is None


def test_koolkid_both_keeps_user_stakes_on_directional_flow(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=100.20,
                price_history=[99.98, 100.00, 100.02, 100.04, 100.07, 100.10, 100.14, 100.20],
            )
        },
        "unchain_hl": {
            "koolkid_both_enabled": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "koolkid_higher_barrier": "+0.10",
            "koolkid_lower_barrier": "-0.14",
            "koolkid_both_simulation": {
                "active": True,
                "symbol": "R_25",
                "start_price": 100.0,
                "current_price": 100.20,
                "started_at": 1.0,
                "check_at": 2.0,
                "ends_at": 16.0,
                "simulation_duration": 15,
                "live_duration": 5,
                "time": "12:00:00",
                "virtual_contract_id": "UNCHAIN-KOOLKID-BOTH-SIM",
                "sides": [
                    {
                        "side": "HIGHER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "+0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-HIGHER",
                    },
                    {
                        "side": "LOWER",
                        "symbol": "R_25",
                        "stake": 10.0,
                        "sim_barrier": "-0.12",
                        "sim_barrier_mag": 0.12,
                        "start_price": 100.0,
                        "contract_id": "UNCHAIN-KOOLKID-BOTH-SIM-LOWER",
                    },
                ],
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(
        server,
        "_compute_unchain_auto_metrics",
        lambda state, u=None: {
            "ready": True,
            "avg_abs_tick_movement": 0.04,
            "current_20_range": 0.22,
            "compression_score": 35.0,
            "momentum_burst_score": 44.0,
            "micro_breakout_score": 26.0,
            "average_tick_interval": 1.8,
            "min_tick_speed": 2.4,
        },
    )
    monkeypatch.setattr(server.time, "time", lambda: 9.5)

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_koolkid_both("cid", state) is True
    assert len(placed) == 2
    assert placed[0]["barrier"] == "+0.1"
    assert placed[1]["barrier"] == "-0.14"
    assert placed[0]["stake"] == 10.0
    assert placed[1]["stake"] == 10.0
    assert state["unchain_hl"]["koolkid_both_simulation"] is None


def test_directional_auto_waits_for_5_tick_sim_before_sending_live_trade(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.02, 100.05, 100.08, 100.12, 100.16, 100.20, 100.24, 100.28, 100.33, 100.38, 100.44],
                tick_time_history=list(range(12)),
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "-0.12",
            "higher_stake": 12.0,
            "lower_stake": 7.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 0
    sim = state["unchain_hl"]["directional_auto_simulation"]
    assert sim is not None
    assert sim["side"] == "HIGHER"
    assert sim["duration"] == 5
    assert sim["duration_unit"] == "t"
    assert sim["stake"] == 12.0

    strat = state["strategies"]["UNCHAIN"]
    strat.price_history.extend([100.48, 100.54, 100.60, 100.67, 100.75])
    strat.tick_time_history.extend(range(12, 17))

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 1
    assert len(placed) == 1
    assert state["unchain_hl"]["directional_auto_simulation"] is None
    assert len(strat.trade_history) == 1
    assert strat.trade_history[0]["type"] == "DIRECTIONAL SIM HIGHER"
    assert strat.trade_history[0]["result"] == "WIN"
    assert placed[0]["side"] == "HIGHER"
    assert placed[0]["barrier"] == "-0.12"
    assert placed[0]["duration"] == 5
    assert placed[0]["duration_unit"] == "t"
    assert placed[0]["stake"] == 12.0
    assert placed[0]["entry_source"] == "DIRECTIONAL_AUTO"
    assert placed[0]["respect_half_barrier_toggle"] is False


def test_directional_auto_both_trades_sends_higher_and_lower_after_sim_win(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.02, 100.05, 100.08, 100.12, 100.16, 100.20, 100.24, 100.28, 100.33, 100.38, 100.44],
                tick_time_history=list(range(12)),
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "directional_auto_both_trades": True,
            "higher_stake": 12.0,
            "lower_stake": 7.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 0
    sim = state["unchain_hl"]["directional_auto_simulation"]
    assert sim is not None
    assert sim["both_trades"] is True

    strat = state["strategies"]["UNCHAIN"]
    strat.price_history.extend([100.48, 100.54, 100.60, 100.67, 100.75])
    strat.tick_time_history.extend(range(12, 17))

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 2
    assert state["unchain_hl"]["directional_auto_simulation"] is None
    assert len(strat.trade_history) == 1
    assert strat.trade_history[0]["type"] == "DIRECTIONAL SIM HIGHER"
    assert {placed[0]["side"], placed[1]["side"]} == {"HIGHER", "LOWER"}
    barriers = {call["side"]: call["barrier"] for call in placed}
    assert barriers["HIGHER"] == "+0.12"
    assert barriers["LOWER"] == "+0.12"
    stakes = {call["side"]: call["stake"] for call in placed}
    assert stakes["HIGHER"] == 12.0
    assert stakes["LOWER"] == 7.0
    assert all(call["entry_source"] == "DIRECTIONAL_AUTO" for call in placed)
    assert all(call["respect_half_barrier_toggle"] is False for call in placed)
    assert all(call["mode"] == "DIRECTIONAL_AUTO_BOTH" for call in placed)


def test_directional_auto_both_trades_reuses_exact_user_barrier_text(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.10, 100.20, 100.30, 100.40, 100.50],
                tick_time_history=list(range(6)),
                tick_count=6,
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "-2.5",
            "directional_auto_both_trades": True,
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "duration": 5,
            "duration_unit": "t",
            "directional_auto_simulation": {
                "active": True,
                "contract_id": "sim-1",
                "side": "HIGHER",
                "barrier": "-2.5",
                "barrier_value": -2.5,
                "stake": 10.0,
                "symbol": "R_25",
                "time": "now",
                "started_at": 0.0,
                    "started_tick": 1,
                "current_tick_count": 0,
                "start_price": 100.0,
                "current_price": 100.0,
                "simulation_ticks": 5,
                "duration": 5,
                "duration_unit": "t",
                "live_duration": 5,
                "live_duration_unit": "t",
                "both_trades": True,
                "final_confidence": 82.0,
            },
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._process_unchain_directional_auto_simulation("cid", state, state["unchain_hl"]) is True
    assert len(placed) == 2
    barriers = {call["side"]: call["barrier"] for call in placed}
    assert barriers["HIGHER"] == "-2.5"
    assert barriers["LOWER"] == "-2.5"


def test_directional_auto_waits_when_selected_lower_side_is_not_favored(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.03, 100.06, 100.10, 100.14, 100.18, 100.23, 100.28, 100.34, 100.40],
                tick_time_history=list(range(10)),
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "LOWER",
            "directional_auto_barrier": "-0.12",
            "higher_stake": 10.0,
            "lower_stake": 10.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    assert server._run_unchain_directional_auto_trade("cid", state) is False
    reason = str(state["unchain_hl"]["directional_auto_last_reason"]).lower()
    assert ("higher" in reason) or ("direction" in reason) or ("tick" in reason)


def test_directional_auto_does_not_double_fire_while_request_is_pending(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.02, 100.05, 100.08, 100.12, 100.16, 100.20, 100.24, 100.28, 100.33, 100.38, 100.44],
                tick_time_history=list(range(12)),
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "higher_stake": 12.0,
            "lower_stake": 7.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert server._run_unchain_directional_auto_trade("cid", state) is False
    assert len(placed) == 0
    assert state["unchain_hl"]["directional_auto_simulation"] is not None
    assert "sim running" in str(state["unchain_hl"]["directional_auto_last_reason"]).lower()


def test_directional_auto_stable_profits_reduces_next_trade_after_two_wins(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.03, 100.07, 100.12, 100.18, 100.25, 100.33, 100.42, 100.52, 100.63, 100.75, 100.88],
                tick_time_history=list(range(12)),
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "directional_auto_stable_profits": True,
            "higher_stake": 100.0,
            "lower_stake": 50.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    server._finalize_unchain_contract(state, {"contract_id": "1", "profit": 8.0}, meta={"entry_source": "DIRECTIONAL_AUTO", "type": "HIGHER"})
    server._finalize_unchain_contract(state, {"contract_id": "2", "profit": 9.0}, meta={"entry_source": "DIRECTIONAL_AUTO", "type": "HIGHER"})
    state["unchain_hl"]["directional_auto_next_fire_at"] = 0.0

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert state["unchain_hl"]["directional_auto_win_streak"] == 2
    assert state["unchain_hl"]["directional_auto_reduce_next_stake"] is True
    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 0
    sim = state["unchain_hl"]["directional_auto_simulation"]
    assert sim is not None
    assert sim["stake"] == 10.0
    strat = state["strategies"]["UNCHAIN"]
    strat.price_history.extend([101.02, 101.15, 101.28, 101.42, 101.58])
    strat.tick_time_history.extend(range(12, 17))
    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 1
    assert placed[0]["stake"] == 10.0
    assert state["unchain_hl"]["directional_auto_reduce_next_stake"] is False
    assert state["unchain_hl"]["directional_auto_win_streak"] == 0
    assert state["unchain_hl"]["directional_auto_simulation"] is None


def test_directional_auto_sim_loss_still_records_history_without_second_live_trade(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                price_history=[100.00, 100.04, 100.08, 100.12, 100.15, 100.19, 100.24, 100.28, 100.31, 100.36, 100.40, 100.44],
                tick_time_history=list(range(12)),
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "higher_stake": 15.0,
            "lower_stake": 10.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }
    placed = []

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)
    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])

    def fake_send(client_id, **kwargs):
        placed.append(kwargs)
        return True, "ok"

    monkeypatch.setattr(server, "_send_unchain_hl_trade", fake_send)

    assert server._run_unchain_directional_auto_trade("cid", state) is True
    assert len(placed) == 0
    strat = state["strategies"]["UNCHAIN"]
    strat.price_history.extend([100.43, 100.41, 100.39, 100.36, 100.32])
    strat.tick_time_history.extend(range(12, 17))

    assert server._run_unchain_directional_auto_trade("cid", state) is False
    assert len(placed) == 0
    assert state["unchain_hl"]["directional_auto_simulation"] is None
    assert len(strat.trade_history) == 1
    assert strat.trade_history[0]["type"] == "DIRECTIONAL SIM HIGHER"
    assert strat.trade_history[0]["result"] == "LOSS"
    assert "skipped the live trade" in str(state["unchain_hl"]["directional_auto_last_reason"]).lower()


def test_directional_auto_status_exposes_live_sim_pnl(monkeypatch):
    state = {
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=100.54,
                price_history=[100.00, 100.08, 100.16, 100.24, 100.32, 100.40, 100.48, 100.54],
                tick_time_history=list(range(8)),
                tick_count=8,
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "directional_auto_simulation": {
                "active": True,
                "contract_id": "UNCHAIN-DIRECTIONAL-SIM-1",
                "side": "HIGHER",
                "barrier": "+0.12",
                "barrier_value": 0.12,
                "stake": 20.0,
                "symbol": "R_25",
                "time": "10:00:00",
                "started_at": 0.0,
                "started_tick": 3,
                "current_tick_count": 8,
                "start_price": 100.10,
                "current_price": 100.54,
                "simulation_ticks": 5,
                "duration": 5,
                "duration_unit": "t",
                "market_confidence": 74.0,
                "simulation_win_rate": 70.0,
                "simulation_confidence": 68.0,
                "final_confidence": 71.0,
                "sample_count": 6,
            },
        },
    }

    payload = server._get_unchain_directional_auto_status(state)

    assert payload["status"] == "SIMULATING"
    assert payload["simulation"]["active"] is True
    assert payload["simulation"]["countdown_remaining"] == 0
    assert float(payload["simulation"]["estimated_pnl"]) > 0.0


def test_directional_auto_sim_stays_active_even_if_live_trade_opens(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "strategies": {
            "UNCHAIN": SimpleNamespace(
                last_price=100.30,
                price_history=[100.00, 100.05, 100.10, 100.14, 100.18, 100.22, 100.26, 100.30],
                tick_time_history=list(range(8)),
                tick_count=8,
                trade_history=[],
            ),
        },
        "unchain_hl": {
            "directional_auto_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
            "directional_auto_simulation": {
                "active": True,
                "contract_id": "UNCHAIN-DIRECTIONAL-SIM-OPEN",
                "side": "HIGHER",
                "barrier": "+0.12",
                "barrier_value": 0.12,
                "stake": 10.0,
                "symbol": "R_25",
                "time": "10:00:00",
                "started_at": 0.0,
                "started_tick": 6,
                "current_tick_count": 8,
                "start_price": 100.10,
                "current_price": 100.30,
                "simulation_ticks": 5,
                "duration": 5,
                "duration_unit": "t",
                "market_confidence": 72.0,
                "simulation_win_rate": 66.0,
                "simulation_confidence": 64.0,
                "final_confidence": 68.0,
                "sample_count": 5,
            },
            "active_contracts": {
                "LIVE-1": {
                    "contract_id": "LIVE-1",
                    "status": "OPEN",
                    "is_sold": False,
                    "type": "HIGHER",
                    "stake": 5.0,
                    "symbol": "R_25",
                    "duration": 5,
                    "duration_unit": "t",
                }
            },
        },
    }

    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)

    assert server._run_unchain_directional_auto_trade("cid", state) is False
    assert state["unchain_hl"]["directional_auto_simulation"] is not None
    assert state["unchain_hl"]["directional_auto_simulation"]["active"] is True
    assert "sim running" in str(state["unchain_hl"]["directional_auto_last_reason"]).lower()


def test_toggle_directional_auto_disables_other_unchain_auto_modes(monkeypatch):
    state = {
        "unchain_hl": {
            "auto_both_enabled": True,
            "ai_auto_trade_enabled": True,
            "koolkid_hl_enabled": True,
            "koolkid_both_enabled": True,
            "directional_auto_side": "HIGHER",
            "directional_auto_barrier": "+0.12",
        }
    }

    monkeypatch.setattr(server, "_get_open_unchain_active_entries", lambda state: [])
    monkeypatch.setattr(server, "_run_unchain_directional_auto_trade", lambda cid, state: False)

    with server.app.app_context():
        response = server._toggle_unchain_directional_auto("cid", state, {"enabled": True})
        data = response.get_json()

    u = state["unchain_hl"]
    assert data["status"] == "success"
    assert u["directional_auto_enabled"] is True
    assert u["auto_both_enabled"] is False
    assert u["ai_auto_trade_enabled"] is False
    assert u["koolkid_hl_enabled"] is False
    assert u["koolkid_both_enabled"] is False
    assert data["payload"]["unchain"]["directional_auto"]["enabled"] is True
