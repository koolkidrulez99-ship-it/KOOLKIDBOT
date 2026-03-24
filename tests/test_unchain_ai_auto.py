import server
import pytest
from types import SimpleNamespace


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
    assert placed[0]["respect_half_barrier_toggle"] is False
    assert state["unchain_hl"]["koolkid_hl_simulation"] is None

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


def test_koolkid_both_places_reduced_barrier_pair_on_strong_movement(monkeypatch):
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
    assert placed[0]["barrier"] == "+0.05"
    assert placed[1]["barrier"] == "-0.07"
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


def test_koolkid_both_rebalances_60_40_on_directional_flow(monkeypatch):
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
    assert placed[0]["stake"] == 12.0
    assert placed[1]["stake"] == 8.0
    assert state["unchain_hl"]["koolkid_both_simulation"] is None
