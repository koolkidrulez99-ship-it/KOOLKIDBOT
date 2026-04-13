from types import SimpleNamespace

import server
from strategies.mutant import NTTStrategy, _format_ntt_barrier
from strategies.mutant_auto import (
    arm_mutant_auto,
    default_mutant_auto_state,
    progress_mutant_auto_after_result,
    stop_mutant_auto,
)


def test_ntt_stats_payload_uses_settled_session_profit():
    strat = NTTStrategy()
    strat.total_wins = 3
    strat.total_losses = 1
    strat.session_profit = 12.75

    payload = strat.get_stats_payload(balance=84.0, session_start_balance=100.0)

    assert payload["net_pnl"] == 12.75
    assert payload["wins"] == 3
    assert payload["losses"] == 1
    assert payload["winrate"] == 75.0
    assert payload["auto_trade"] is False


def test_format_ntt_barrier_rounds_to_two_decimals():
    assert _format_ntt_barrier("8.1334", "TOUCH", "t") == "+8.13"
    assert _format_ntt_barrier("-8.136", "NO_TOUCH", "t") == "-8.14"


def test_build_ntt_expected_profit_preview_uses_best_pair_payout(monkeypatch):
    def fake_quote(state, *, side, stake, symbol, barrier, duration, duration_unit="t", timeout_sec=1.6):
        if side == "TOUCH":
            return {"ask_price": 10.0, "payout": 18.0, "barrier": barrier}, None
        return {"ask_price": 10.0, "payout": 16.0, "barrier": barrier}, None

    monkeypatch.setattr(server, "_request_ntt_proposal_quote", fake_quote)

    preview = server._build_ntt_expected_profit_preview(
        {},
        symbol="R_10",
        touch_stake=10.0,
        no_touch_stake=10.0,
        touch_barrier="+0.17",
        no_touch_barrier="+0.17",
        duration=5,
        duration_unit="t",
    )

    assert preview["touch"]["profit"] == 8.0
    assert preview["no_touch"]["profit"] == 6.0
    assert preview["both"]["total_stake"] == 20.0
    assert preview["both"]["net_profit"] == -2.0


def test_ntt_trade_route_supports_both(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_10",
        "active_profile": "NTT",
        "strategies": {
            "NTT": SimpleNamespace(
                get_stats_payload=lambda balance, start: {"wins": 0, "losses": 0, "net_pnl": 0.0},
                get_bias_payload=lambda config=None: {"touch_pct": 50.0, "no_touch_pct": 50.0},
                last_price=100.0,
            )
        },
        "ntt": {
            "touch_stake": 5.0,
            "no_touch_stake": 5.0,
            "touch_barrier": "+0.17",
            "no_touch_barrier": "+0.17",
            "duration": 5,
            "duration_unit": "t",
            "active_contracts": {},
        },
    }
    sent = []

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-ntt", state))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    def fake_send(client_id, state, **kwargs):
        sent.append(kwargs)
        return True, "ok", ["TOUCH", "NO_TOUCH"]

    monkeypatch.setattr(server, "_send_ntt_both_pair", fake_send)

    with server.app.test_client() as client:
        response = client.post(
            "/ntt_trade",
            json={
                "side": "BOTH",
                "symbol": "R_10",
                "touch_stake": 5.0,
                "no_touch_stake": 5.0,
                "touch_barrier": "+0.17",
                "no_touch_barrier": "+0.17",
                "duration": 5,
                "duration_unit": "t",
            },
        )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["placed"] == ["TOUCH", "NO_TOUCH"]
    assert len(sent) == 1
    assert sent[0]["touch_stake"] == 5.0
    assert sent[0]["no_touch_stake"] == 5.0
    assert sent[0]["touch_duration"] == 5
    assert sent[0]["no_touch_duration"] == 5


def test_ntt_status_route_refreshes_barriers_on_market_switch(monkeypatch):
    state = {
        "current_symbol": "R_25",
        "ntt": {
            "market_default_symbol": "R_10",
        },
    }
    applied = []

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-ntt", state))
    monkeypatch.setattr(server, "_ensure_tick_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_apply_ntt_market_default_barriers", lambda _state, symbol: applied.append(symbol) or (True, "+0.19 / +0.19"))
    monkeypatch.setattr(server, "_ntt_payload_response", lambda _state: {"ntt": {"touch_barrier": "+0.19", "no_touch_barrier": "+0.19"}})

    with server.app.test_client() as client:
        response = client.get("/ntt_status")

    payload = response.get_json()
    assert response.status_code == 200
    assert applied == ["R_25"]
    assert payload["ntt"]["touch_barrier"] == "+0.19"


def test_process_tick_calls_ntt_countdown_manager_on_main_market(monkeypatch):
    called = []

    class DummyStrategy:
        tick_count = 0

        def on_tick(self, *_args, **_kwargs):
            return None

        def get_ui_payload(self):
            return {}

    state = {
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "active_profile": "KOOLKID",
        "strategies": {
            "KOOLKID": DummyStrategy(),
            "NTT": DummyStrategy(),
        },
    }

    monkeypatch.setattr(server, "clients", {"cid-ntt": state})
    monkeypatch.setattr(server, "extract_last_decimal_digit", lambda *_args, **_kwargs: 5)
    monkeypatch.setattr(server, "_maybe_unchain_exit_on_tick", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_force_unchain_close_on_countdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_force_ntt_close_on_countdown", lambda client_id, _state: called.append(client_id))
    monkeypatch.setattr(server, "run_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_ai_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_auto_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_directional_auto_trade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_koolkid_hl", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_unchain_koolkid_both", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    server.process_tick("cid-ntt", {"symbol": "R_10", "quote": 100.12, "pip_size": 2})

    assert called == ["cid-ntt"]


def test_apply_ntt_settings_update_mirrors_touch_stake_to_no_touch():
    state = {"ntt": {"touch_stake": 1.0, "no_touch_stake": 2.5}}

    updated = server._apply_ntt_settings_update(state, {"touch_stake": 3.75})

    assert updated["touch_stake"] == 3.75
    assert updated["no_touch_stake"] == 2.5


def test_apply_ntt_settings_update_allows_manual_no_touch_override():
    state = {"ntt": {"touch_stake": 3.75, "no_touch_stake": 3.75}}

    updated = server._apply_ntt_settings_update(state, {"no_touch_stake": 10.0})

    assert updated["touch_stake"] == 3.75
    assert updated["no_touch_stake"] == 10.0


def test_apply_ntt_settings_update_supports_side_specific_durations():
    state = {"ntt": {"duration": 5, "duration_unit": "t"}}

    updated = server._apply_ntt_settings_update(
        state,
        {
            "use_shared_duration": False,
            "touch_duration": 6,
            "touch_duration_unit": "t",
            "no_touch_duration": 3,
            "no_touch_duration_unit": "m",
        },
    )

    assert updated["use_shared_duration"] is False
    assert updated["touch_duration"] == 6
    assert updated["touch_duration_unit"] == "t"
    assert updated["no_touch_duration"] == 3
    assert updated["no_touch_duration_unit"] == "m"


def test_apply_ntt_settings_update_marks_current_market_when_manual_barriers_change():
    state = {
        "current_symbol": "R_25",
        "ntt": {
            "duration": 5,
            "duration_unit": "t",
            "touch_barrier": "+0.12",
            "no_touch_barrier": "+0.12",
        },
    }

    updated = server._apply_ntt_settings_update(
        state,
        {
            "touch_barrier": "+0.19",
            "no_touch_barrier": "+0.27",
        },
    )

    assert updated["touch_barrier"] == "+0.19"
    assert updated["no_touch_barrier"] == "+0.27"
    assert updated["market_default_symbol"] == "R_25"
    assert updated["market_default_key"] == "R_25|5|T"


def test_apply_ntt_market_default_barriers_uses_side_durations_when_shared_off(monkeypatch):
    calls = []
    state = {
        "current_symbol": "R_10",
        "ntt": {
            "use_shared_duration": False,
            "touch_duration": 5,
            "touch_duration_unit": "t",
            "no_touch_duration": 7,
            "no_touch_duration_unit": "t",
        },
    }

    def fake_fetch(symbol, duration, duration_unit):
        calls.append((symbol, duration, duration_unit))
        return "0.17", None

    monkeypatch.setattr(server, "_fetch_ntt_market_default_barrier", fake_fetch)

    ok, _msg = server._apply_ntt_market_default_barriers(state, "R_10")

    assert ok is True
    assert calls == [("R_10", 5, "t"), ("R_10", 7, "t")]
    assert state["ntt"]["touch_barrier"] == "+0.17"
    assert state["ntt"]["no_touch_barrier"] == "+0.17"


def test_ntt_trade_route_both_uses_side_specific_durations_when_shared_off(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "balance": 100.0,
        "current_symbol": "R_10",
        "active_profile": "NTT",
        "strategies": {
            "NTT": SimpleNamespace(
                get_stats_payload=lambda balance, start: {"wins": 0, "losses": 0, "net_pnl": 0.0},
                get_bias_payload=lambda config=None: {"touch_pct": 50.0, "no_touch_pct": 50.0},
                last_price=100.0,
            )
        },
        "ntt": {
            "use_shared_duration": False,
            "touch_stake": 5.0,
            "no_touch_stake": 5.0,
            "touch_barrier": "+0.17",
            "no_touch_barrier": "+0.17",
            "duration": 5,
            "duration_unit": "t",
            "touch_duration": 5,
            "touch_duration_unit": "t",
            "no_touch_duration": 7,
            "no_touch_duration_unit": "t",
            "active_contracts": {},
        },
    }
    sent = []

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-ntt", state))
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        server,
        "_send_ntt_both_pair",
        lambda client_id, state, **kwargs: sent.append(kwargs) or (True, "ok", ["TOUCH", "NO_TOUCH"]),
    )

    with server.app.test_client() as client:
        response = client.post(
            "/ntt_trade",
            json={
                "side": "BOTH",
                "symbol": "R_10",
                "use_shared_duration": False,
                "touch_stake": 5.0,
                "no_touch_stake": 5.0,
                "touch_barrier": "+0.17",
                "no_touch_barrier": "+0.17",
                "duration": 5,
                "duration_unit": "t",
                "touch_duration": 5,
                "touch_duration_unit": "t",
                "no_touch_duration": 7,
                "no_touch_duration_unit": "t",
            },
        )

    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0]["touch_duration"] == 5
    assert sent[0]["touch_duration_unit"] == "t"
    assert sent[0]["no_touch_duration"] == 7
    assert sent[0]["no_touch_duration_unit"] == "t"


def test_normalize_ntt_trade_type_maps_touch_and_no_touch_labels():
    assert server._normalize_ntt_trade_type("TOUCH", None) == "TOUCH"
    assert server._normalize_ntt_trade_type("NO_TOUCH", None) == "NO TOUCH"
    assert server._normalize_ntt_trade_type("accum auto", "ONETOUCH") == "TOUCH"
    assert server._normalize_ntt_trade_type("accum auto", "NOTOUCH") == "NO TOUCH"


def test_finalize_ntt_contract_overrides_inherited_trade_label_with_ntt_side():
    class DummyStrategy:
        risk_block_reason = None

        def on_contract(self, *_args, **_kwargs):
            return None

        def get_last_trade_entry(self):
            return {
                "profile": "UNCHAIN",
                "type": "ACCU AUTO",
                "result": "PENDING",
            }

    state = {
        "strategies": {"NTT": DummyStrategy()},
        "ntt": {"active_contracts": {}},
    }

    entry = server._finalize_ntt_contract(
        state,
        {"contract_id": "12345", "status": "sold", "profit": 4.5, "contract_type": "NOTOUCH"},
        104.5,
        meta={
            "type": "NO_TOUCH",
            "barrier": "+0.17",
            "stake": 1.0,
            "symbol": "R_10",
            "time": "12:00:00",
            "duration": 5,
            "duration_unit": "t",
            "deriv_contract_type": "NOTOUCH",
        },
    )

    assert entry["profile"] == "NTT"
    assert entry["type"] == "NO TOUCH"
    assert state["ntt"]["last_result"]["type"] == "NO TOUCH"


def test_serialize_ntt_koolkid_hl_maps_touch_labels(monkeypatch):
    monkeypatch.setattr(
        server,
        "_serialize_unchain_koolkid_hl",
        lambda _state, _u=None, active_count=None: {
            "enabled": True,
            "last_reason": "KOOLKID Higher/Lower armed.",
            "label": "HIGHER / LOWER",
            "sim_side": "HIGHER",
            "reversal_enabled": True,
            "half_barrier_enabled": False,
            "simulation": {
                "side": "HIGHER",
                "opposite_side": "LOWER",
                "message": "Higher will flip into Lower if the sim loses.",
                "sides": [
                    {"side": "HIGHER", "contract_id": "UNCHAIN-1"},
                    {"side": "LOWER", "contract_id": "UNCHAIN-2"},
                ],
            },
        },
    )

    payload = server._serialize_ntt_koolkid_hl(
        {
            "strategies": {"NTT": object()},
            "ntt": {
                "touch_stake": 1.0,
                "no_touch_stake": 1.0,
                "touch_barrier": "+0.17",
                "no_touch_barrier": "+0.17",
                "duration": 5,
                "duration_unit": "t",
                "koolkid_touch_barrier": "+0.06",
                "koolkid_no_touch_barrier": "+0.06",
                "koolkid_hl_enabled": True,
                "koolkid_reversal_enabled": True,
            },
        }
    )

    assert payload["sim_side"] == "TOUCH"
    assert "Touch/No Touch" in payload["last_reason"]
    assert payload["simulation"]["side"] == "TOUCH"
    assert payload["simulation"]["opposite_side"] == "NO_TOUCH"
    assert payload["simulation"]["sides"][0]["contract_id"] == "MUTANT-1"


def test_toggle_ntt_koolkid_hl_turns_off_both_and_sets_reason(monkeypatch):
    emitted = []
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(server, "_run_ntt_koolkid_hl", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(server, "_ntt_payload_response", lambda _state: {"ntt": {"ok": True}})

    state = {
        "active_profile": "NTT",
        "ntt": {
            "touch_stake": 1.0,
            "no_touch_stake": 1.0,
            "touch_barrier": "+0.17",
            "no_touch_barrier": "+0.17",
            "duration": 5,
            "duration_unit": "t",
            "koolkid_both_enabled": True,
        },
    }

    with server.app.app_context():
        response = server._toggle_ntt_koolkid_hl("cid-mutant", state, {"enabled": True})

    payload = response.get_json()
    assert payload["status"] == "success"
    assert state["ntt"]["koolkid_hl_enabled"] is True
    assert state["ntt"]["koolkid_both_enabled"] is False
    assert "Touch/No Touch armed" in state["ntt"]["koolkid_hl_last_reason"]


def test_toggle_ntt_auto_both_turns_on_and_off(monkeypatch):
    emitted = []
    run_calls = []

    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(server, "_run_ntt_auto_both", lambda cid, _state: run_calls.append(cid) or False)
    monkeypatch.setattr(
        server,
        "_ntt_payload_response",
        lambda _state: {"ntt": {"auto_both": server._serialize_ntt_auto_both(_state)}},
    )

    state = {
        "active_profile": "NTT",
        "ntt": server._default_ntt_state(),
    }
    state["ntt"]["koolkid_hl_enabled"] = True
    state["ntt"]["koolkid_both_enabled"] = True

    with server.app.app_context():
        enabled_response = server._toggle_ntt_auto_both(
            "cid-mutant",
            state,
            {
                "enabled": True,
                "barrier": "+0.23",
                "budget": 10,
                "selected_side": "NO_TOUCH",
                "martingale_enabled": True,
                "step50_enabled": True,
            },
        )
        disabled_response = server._toggle_ntt_auto_both("cid-mutant", state, {"enabled": False})

    enabled_payload = enabled_response.get_json()
    disabled_payload = disabled_response.get_json()
    auto = state["ntt"]["auto"]

    assert enabled_payload["status"] == "success"
    assert enabled_payload["enabled"] is True
    assert "MUTANT AUTO ON" == enabled_payload["message"]
    assert run_calls == ["cid-mutant"]
    assert state["ntt"]["koolkid_hl_enabled"] is False
    assert state["ntt"]["koolkid_both_enabled"] is False
    assert auto["barrier"] == "+0.23"
    assert auto["budget"] == 10.0
    assert auto["selected_side"] == "NO_TOUCH"
    assert auto["martingale_enabled"] is True
    assert auto["step50_enabled"] is False

    assert disabled_payload["status"] == "success"
    assert disabled_payload["enabled"] is False
    assert "MUTANT AUTO OFF" == disabled_payload["message"]
    assert state["ntt"]["auto"]["enabled"] is False
    assert emitted


def test_run_ntt_auto_both_sends_single_fast_trade_with_request_lock(monkeypatch):
    sent = []
    monkeypatch.setattr(server, "_check_ntt_risk_block", lambda _state: None)
    monkeypatch.setattr(server, "_get_ntt_side_duration", lambda _ntt, _side: (5, "t"))
    monkeypatch.setattr(
        server,
        "_send_ntt_trade",
        lambda cid, **kwargs: sent.append((cid, kwargs)) or (True, "Trade sent"),
    )

    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "ntt": server._default_ntt_state(),
    }
    arm_mutant_auto(state["ntt"], barrier="+0.19", budget=10.0, selected_side="NO_TOUCH", martingale_enabled=False, step50_enabled=False)

    ok = server._run_ntt_auto_both("cid-mutant", state)
    auto = state["ntt"]["auto"]

    assert ok is True
    assert len(sent) == 1
    assert sent[0][0] == "cid-mutant"
    assert sent[0][1]["side"] == "NO_TOUCH"
    assert sent[0][1]["stake"] == 10.0
    assert sent[0][1]["mode"] == "MUTANT_AUTO"
    assert sent[0][1]["emit_balance"] is False
    assert sent[0][1]["extra_meta"]["auto_mode"] == "BASE"
    assert sent[0][1]["extra_meta"]["auto_current_stake"] == 10.0
    assert sent[0][1]["extra_meta"]["auto_step_index"] == 0
    assert auto["request_in_flight"] is True
    assert auto["active_side"] == "NO_TOUCH"
    assert auto["active_symbol"] == "R_25"


def test_run_ntt_auto_both_sends_frozen_ladder_plan_meta(monkeypatch):
    sent = []
    monkeypatch.setattr(server, "_check_ntt_risk_block", lambda _state: None)
    monkeypatch.setattr(server, "_get_ntt_side_duration", lambda _ntt, _side: (5, "t"))
    monkeypatch.setattr(
        server,
        "_send_ntt_trade",
        lambda cid, **kwargs: sent.append((cid, kwargs)) or (True, "Trade sent"),
    )

    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "ntt": server._default_ntt_state(),
    }
    arm_mutant_auto(state["ntt"], barrier="+0.19", budget=10.0, selected_side="TOUCH", martingale_enabled=False, step50_enabled=True)
    state["ntt"]["auto"]["progression_step"] = 1
    state["ntt"]["auto"]["current_stake"] = 0.85

    ok = server._run_ntt_auto_both("cid-mutant", state)
    meta = sent[0][1]["extra_meta"]

    assert ok is True
    assert sent[0][1]["stake"] == 0.85
    assert meta["auto_mode"] == "STEP50"
    assert meta["auto_mode_label"] == "50 CENTS MARTINGALE"
    assert meta["auto_step_index"] == 1
    assert meta["auto_current_stake"] == 0.85
    assert meta["auto_next_loss_stake"] == 1.35
    assert meta["auto_stop_on_win"] is True
    assert meta["auto_stop_on_loss"] is False
    assert state["ntt"]["auto"]["active_step_index"] == 1
    assert state["ntt"]["auto"]["active_next_loss_stake"] == 1.35


def test_run_ntt_auto_both_prelocks_before_send_so_reentry_cannot_double_fire(monkeypatch):
    sent = []
    nested_results = []

    monkeypatch.setattr(server, "_check_ntt_risk_block", lambda _state: None)
    monkeypatch.setattr(server, "_get_ntt_side_duration", lambda _ntt, _side: (5, "t"))

    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_25",
        "ntt": server._default_ntt_state(),
    }
    arm_mutant_auto(
        state["ntt"],
        barrier="+0.19",
        budget=10.0,
        selected_side="TOUCH",
        martingale_enabled=True,
        step50_enabled=False,
    )

    def fake_send(cid, **kwargs):
        nested_results.append(server._run_ntt_auto_both(cid, state))
        sent.append((cid, kwargs))
        return True, "Trade sent"

    monkeypatch.setattr(server, "_send_ntt_trade", fake_send)

    ok = server._run_ntt_auto_both("cid-mutant", state)
    auto = state["ntt"]["auto"]

    assert ok is True
    assert len(sent) == 1
    assert nested_results == [False]
    assert auto["request_in_flight"] is True
    assert auto["active_side"] == "TOUCH"
    assert auto["current_stake"] == 0.35


def test_set_profile_leaves_mutant_unlocked_when_access_is_available(monkeypatch):
    state = {
        "strategies": {"NTT": object()},
        "current_symbol": "R_10",
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-ntt", state))
    monkeypatch.setattr(server, "_ensure_tick_subscription", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "emit_profile_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_mutant_access_state", lambda: {
        "enabled": True,
        "under_construction": False,
        "local": False,
        "email_override": False,
        "user_email": "someone@example.com",
        "message": "",
    })

    with server.app.test_client() as client:
        response = client.post("/set_profile", json={"profile": "NTT"})

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["mutant_locked"] is False
    assert payload["mutant_access"]["enabled"] is True


def test_mutant_access_state_is_available_to_everyone_even_when_gate_flag_is_on(monkeypatch):
    monkeypatch.setattr(server, "MUTANT_DEPLOY_GATE_ENABLED", True)
    monkeypatch.setattr(server, "MUTANT_ALLOWED_ACCOUNT", "")
    monkeypatch.setattr(server, "_request_host_is_local", lambda: False)
    monkeypatch.setattr(server, "_get_user_row", lambda _username: None)

    with server.app.test_request_context("/"):
        access = server._mutant_access_state()

    assert access["enabled"] is True
    assert access["under_construction"] is False
    assert access["message"] == ""


def test_mutant_access_state_allows_configured_username_override(monkeypatch):
    monkeypatch.setattr(server, "MUTANT_DEPLOY_GATE_ENABLED", True)
    monkeypatch.setattr(server, "MUTANT_ALLOWED_ACCOUNT", "koolkidrulez99@gmail.com")
    monkeypatch.setattr(server, "_request_host_is_local", lambda: False)
    monkeypatch.setattr(
        server,
        "_get_user_row",
        lambda username: {"username": username, "email": "someone@example.com"},
    )

    with server.app.test_request_context("/"):
        server.session["user"] = "koolkidrulez99@gmail.com"
        access = server._mutant_access_state()

    assert access["enabled"] is True
    assert access["username_override"] is True
    assert access["email_override"] is False
    assert access["under_construction"] is False


def test_run_ntt_auto_both_waits_until_open_pair_finishes(monkeypatch):
    send_attempts = []
    monkeypatch.setattr(server, "_check_ntt_risk_block", lambda _state: None)
    monkeypatch.setattr(
        server,
        "_send_ntt_trade",
        lambda *_args, **_kwargs: send_attempts.append(True) or (True, "sent"),
    )

    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_10",
        "ntt": server._default_ntt_state(),
    }
    arm_mutant_auto(state["ntt"], barrier="+0.17", budget=10.0, martingale_enabled=False, step50_enabled=False)
    state["ntt"]["active_contracts"] = {
        "123": {
            "contract_id": "123",
            "type": "TOUCH",
            "status": "open",
            "stake": 1.0,
            "duration": 5,
            "duration_unit": "t",
        }
    }

    ok = server._run_ntt_auto_both("cid-mutant", state)

    assert ok is False
    assert send_attempts == []
    assert "waiting for 1 active Mutant trade to finish" in state["ntt"]["auto"]["last_reason"]


def test_run_ntt_auto_both_clears_stale_tick_pending_and_sends_next_trade(monkeypatch):
    sent = []

    monkeypatch.setattr(server, "_check_ntt_risk_block", lambda _state: None)
    monkeypatch.setattr(server, "_get_ntt_side_duration", lambda _ntt, _side: (5, "t"))
    monkeypatch.setattr(
        server,
        "_send_ntt_trade",
        lambda cid, **kwargs: sent.append((cid, kwargs)) or (True, "sent"),
    )
    monkeypatch.setattr(server.time, "time", lambda: 100.0)

    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_10",
        "ntt": server._default_ntt_state(),
    }
    arm_mutant_auto(state["ntt"], barrier="+0.17", budget=10.0, martingale_enabled=True, step50_enabled=False)
    state["ntt"]["auto"]["pending_contract_id"] = "123"
    state["ntt"]["auto"]["request_in_flight"] = False
    state["ntt"]["auto"]["last_started_at"] = 90.0

    ok = server._run_ntt_auto_both("cid-mutant", state)

    assert ok is True
    assert len(sent) == 1
    assert state["ntt"]["auto"]["request_in_flight"] is True
    assert state["ntt"]["auto"]["pending_contract_id"] is None
    assert "re-arming now" in state["ntt"]["auto"]["last_reason"] or "sent" in state["ntt"]["auto"]["last_reason"].lower()


def test_mutant_auto_base_mode_continues_after_win_and_stops_after_loss():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=10.0, martingale_enabled=False, step50_enabled=False)
    auto = ntt["auto"]
    auto["active_stake"] = 10.0
    auto["active_side"] = "TOUCH"

    win_result = progress_mutant_auto_after_result(ntt, won=True, profit=9.0, side="TOUCH")
    assert win_result["continue"] is True
    assert win_result["next_stake"] == 10.0
    assert ntt["auto"]["enabled"] is True

    auto["active_stake"] = 10.0
    auto["active_side"] = "TOUCH"
    loss_result = progress_mutant_auto_after_result(ntt, won=False, profit=-10.0, side="TOUCH")
    assert loss_result["continue"] is False
    assert loss_result["stopped"] is True
    assert ntt["auto"]["enabled"] is False


def test_mutant_auto_martingale_doubles_after_loss_and_stops_after_win():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=10.0, martingale_enabled=True, step50_enabled=False)
    auto = ntt["auto"]
    auto["active_stake"] = 0.35
    auto["active_side"] = "NO_TOUCH"

    loss_result = progress_mutant_auto_after_result(ntt, won=False, profit=-0.35, side="NO_TOUCH")
    assert loss_result["continue"] is True
    assert loss_result["next_stake"] == 0.70
    assert ntt["auto"]["current_stake"] == 0.70

    auto["active_stake"] = 0.70
    auto["active_side"] = "NO_TOUCH"
    win_result = progress_mutant_auto_after_result(ntt, won=True, profit=0.63, side="NO_TOUCH")
    assert win_result["continue"] is False
    assert ntt["auto"]["enabled"] is False


def test_process_contract_rearms_mutant_auto_after_martingale_loss(monkeypatch):
    reruns = []

    monkeypatch.setattr(server, "send_stats_update", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_seqvix_jokerjoe_on_contract_settled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "handle_auto_session_contract_settled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_run_ntt_auto_both", lambda cid, state: reruns.append((cid, state["ntt"]["auto"]["current_stake"])) or True)

    state = {
        "balance": 100.0,
        "active_profile": "NTT",
        "current_symbol": "R_25",
        "ntt": server._default_ntt_state(),
        "strategies": {
            "NTT": SimpleNamespace(
                on_contract=lambda contract, balance: None,
                get_last_trade_entry=lambda: {},
                risk_block_reason=None,
            )
        },
        "contract_meta": {},
    }
    server.clients["cid-mutant-auto"] = state
    try:
        arm_mutant_auto(state["ntt"], barrier="+0.12", budget=10.0, selected_side="TOUCH", martingale_enabled=True, step50_enabled=False)
        state["ntt"]["auto"]["active_stake"] = 0.35
        state["ntt"]["auto"]["active_side"] = "TOUCH"
        state["ntt"]["auto"]["pending_contract_id"] = "321"
        state["ntt"]["active_contracts"] = {
            "321": {"contract_id": "321", "status": "open", "type": "TOUCH"}
        }
        state["contract_meta"]["321"] = {
            "profile": "NTT",
            "type": "TOUCH",
            "stake": 0.35,
            "symbol": "R_25",
            "time": "now",
            "duration": 5,
            "duration_unit": "t",
            "mode": "MUTANT_AUTO",
        }

        server.process_contract(
            "cid-mutant-auto",
            {
                "contract_id": "321",
                "status": "sold",
                "is_sold": True,
                "profit": -0.35,
                "buy_price": 0.35,
            },
        )
    finally:
        server.clients.pop("cid-mutant-auto", None)

    assert state["ntt"]["auto"]["enabled"] is True
    assert state["ntt"]["auto"]["current_stake"] == 0.70
    assert reruns == [("cid-mutant-auto", 0.70)]


def test_mutant_auto_step50_increments_by_fifty_cents_for_each_loss_chain():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=3.00, martingale_enabled=False, step50_enabled=True)
    auto = ntt["auto"]

    auto["active_stake"] = 0.35
    auto["active_side"] = "TOUCH"
    first_loss = progress_mutant_auto_after_result(ntt, won=False, profit=-0.35, side="TOUCH")

    assert first_loss["continue"] is True
    assert ntt["auto"]["current_stake"] == 0.85

    auto["active_stake"] = 0.85
    auto["active_side"] = "TOUCH"
    second_loss = progress_mutant_auto_after_result(ntt, won=False, profit=-0.85, side="TOUCH")

    assert second_loss["continue"] is True
    assert ntt["auto"]["current_stake"] == 1.35

    auto["active_stake"] = 1.35
    auto["active_side"] = "TOUCH"
    third_loss = progress_mutant_auto_after_result(ntt, won=False, profit=-1.35, side="TOUCH")

    assert third_loss["continue"] is True
    assert ntt["auto"]["current_stake"] == 1.85


def test_mutant_auto_step50_repeats_top_allowed_stake_at_budget_cap():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=1.00, martingale_enabled=False, step50_enabled=True)
    auto = ntt["auto"]
    auto["active_stake"] = 0.35
    auto["active_side"] = "TOUCH"

    first_loss = progress_mutant_auto_after_result(ntt, won=False, profit=-0.35, side="TOUCH")
    assert first_loss["continue"] is True
    assert first_loss["next_stake"] == 0.85
    assert ntt["auto"]["current_stake"] == 0.85

    auto["active_stake"] = 0.85
    auto["active_side"] = "TOUCH"
    second_loss = progress_mutant_auto_after_result(ntt, won=False, profit=-0.85, side="TOUCH")
    assert second_loss["continue"] is True
    assert second_loss["stopped"] is False
    assert second_loss["next_stake"] == 0.85
    assert ntt["auto"]["enabled"] is True
    assert ntt["auto"]["current_stake"] == 0.85


def test_mutant_auto_martingale_repeats_top_allowed_stake_at_budget_cap():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=2000.0, martingale_enabled=True, step50_enabled=False)
    auto = ntt["auto"]
    auto["progression_step"] = 12
    auto["current_stake"] = 1433.60
    auto["active_stake"] = 1433.60
    auto["active_side"] = "TOUCH"

    result = progress_mutant_auto_after_result(ntt, won=False, profit=-1433.60, side="TOUCH")

    assert result["continue"] is True
    assert result["stopped"] is False
    assert result["next_stake"] == 1433.60
    assert ntt["auto"]["enabled"] is True
    assert ntt["auto"]["progression_step"] == 12
    assert ntt["auto"]["current_stake"] == 1433.60


def test_arm_mutant_auto_resets_progression_back_to_base_stake():
    ntt = {"auto": default_mutant_auto_state()}
    auto = ntt["auto"]
    auto["current_stake"] = 2.80

    arm_mutant_auto(ntt, barrier="+0.12", budget=10.0, martingale_enabled=True, step50_enabled=False)

    assert ntt["auto"]["current_stake"] == 0.35


def test_stop_mutant_auto_resets_progression_back_to_base_stake():
    ntt = {"auto": default_mutant_auto_state()}
    arm_mutant_auto(ntt, barrier="+0.12", budget=10.0, martingale_enabled=False, step50_enabled=True)
    ntt["auto"]["current_stake"] = 1.85

    stop_mutant_auto(ntt, "Stopped by user.")

    assert ntt["auto"]["enabled"] is False
    assert ntt["auto"]["current_stake"] == 0.35


def test_send_ntt_both_pair_blocks_when_pair_send_already_in_flight(monkeypatch):
    send_attempts = []
    monkeypatch.setattr(
        server,
        "_send_ntt_trade",
        lambda *args, **kwargs: send_attempts.append((args, kwargs)) or (True, "ok"),
    )

    state = {
        "balance": 50.0,
        "ntt": {
            "pair_send_in_flight": True,
            "touch_stake": 2.0,
            "no_touch_stake": 2.0,
            "touch_barrier": "+0.17",
            "no_touch_barrier": "+0.17",
            "duration": 5,
            "duration_unit": "t",
        },
    }

    ok, msg, placed = server._send_ntt_both_pair(
        "cid-mutant",
        state,
        symbol="R_10",
        duration=5,
        duration_unit="t",
        touch_stake=2.0,
        no_touch_stake=2.0,
        touch_barrier="+0.17",
        no_touch_barrier="+0.17",
    )

    assert ok is False
    assert placed == []
    assert "already sending" in msg
    assert send_attempts == []
