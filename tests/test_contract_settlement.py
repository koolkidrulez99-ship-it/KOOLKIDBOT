import json
import time

import pytest
from types import SimpleNamespace

import server
from server import (
    _apply_unchain_market_default_barriers,
    _ensure_unchain_hl_state,
    _decorate_unchain_active_entry_countdown,
    _format_unchain_barrier,
    _format_unchain_market_default_barrier,
    _get_profile_trade_history_snapshot,
    _get_unchain_visible_barrier,
    _half_unchain_barrier,
    _is_contract_settled_fast,
    _serialize_profile_trade_history_entry,
    _send_unchain_hl_trade,
    _upsert_unchain_active_contract,
    process_contract,
)


@pytest.mark.parametrize(
    "contract",
    [
        {"is_sold": True},
        {"is_settled": True},
        {"status": "sold"},
        {"status": "won"},
        {"status": "lost"},
        {"status": "settled"},
        {"status": "closed"},
        {"status": "expired"},
        {"status": "cancelled"},
        {"status": "canceled"},
        {"sell_price": 0},
        {"sell_price": 1.25},
    ],
)
def test_is_contract_settled_fast_true(contract):
    assert _is_contract_settled_fast(contract) is True


@pytest.mark.parametrize(
    "contract",
    [
        {},
        {"status": "open"},
        {"status": "purchase"},
        {"status": "close requested"},
        {"sell_price": ""},
        {"sell_price": None},
    ],
)
def test_is_contract_settled_fast_false(contract):
    assert _is_contract_settled_fast(contract) is False


def test_tick_countdown_prefers_contract_tick_count_over_sequence_fallback():
    entry = {
        "duration": 10,
        "duration_unit": "t",
        "tick_count": 3,
        "open_tick_seq": 100,
    }
    state = {"strategies": {"UNCHAIN": SimpleNamespace(tick_count=106)}}
    out = _decorate_unchain_active_entry_countdown(entry, state, now_ts=1_700_000_000)
    assert out["countdown_unit"] == "t"
    assert out["countdown_remaining"] == 7


def test_tick_countdown_prefers_deduped_contract_elapsed_ticks():
    entry = {
        "duration": 10,
        "duration_unit": "t",
        "_elapsed_contract_ticks": 4,
        "open_tick_seq": 100,
    }
    state = {"strategies": {"UNCHAIN": SimpleNamespace(tick_count=108)}}
    out = _decorate_unchain_active_entry_countdown(entry, state, now_ts=1_700_000_000)
    assert out["countdown_unit"] == "t"
    assert out["countdown_remaining"] == 6


def test_upsert_unchain_active_contract_dedupes_duplicate_spot_times():
    state = {
        "strategies": {"UNCHAIN": SimpleNamespace(tick_count=250, last_price=7215.5)},
        "current_symbol": "1HZ30V",
        "unchain_hl": {"active_contracts": {}, "stats": {"wins": 0, "losses": 0, "net_pnl": 0.0}},
    }
    meta = {
        "type": "HIGHER",
        "symbol": "1HZ30V",
        "stake": 1.0,
        "duration": 5,
        "duration_unit": "t",
    }

    first = _upsert_unchain_active_contract(
        state,
        contract_id=123456,
        meta=meta,
        contract={"current_spot": 7215.6, "current_spot_time": 1000, "tick_count": 0},
        status="OPEN",
    )
    first_elapsed = first.get("_elapsed_contract_ticks")
    second = _upsert_unchain_active_contract(
        state,
        contract_id=123456,
        meta=meta,
        contract={"current_spot": 7215.6, "current_spot_time": 1000, "tick_count": 0},
        status="OPEN",
    )
    second_elapsed = second.get("_elapsed_contract_ticks")
    third = _upsert_unchain_active_contract(
        state,
        contract_id=123456,
        meta=meta,
        contract={"current_spot": 7215.7, "current_spot_time": 1001, "tick_count": 1},
        status="OPEN",
    )

    assert first_elapsed == 0
    assert second_elapsed == 0
    assert third.get("_elapsed_contract_ticks") == 1


def test_format_unchain_barrier_keeps_user_typed_plus_sign():
    assert _format_unchain_barrier("+0.12", "HIGHER", "t") == "+0.12"


def test_format_unchain_barrier_auto_adds_plus_for_unsigned_tick_units():
    assert _format_unchain_barrier("0.12", "HIGHER", "t") == "+0.12"


def test_half_unchain_barrier_halves_higher_and_lower_values():
    assert _half_unchain_barrier("+0.12", "HIGHER", "t") == "+0.06"
    assert _half_unchain_barrier("-0.12", "LOWER", "t") == "-0.06"


def test_get_unchain_visible_barrier_respects_saved_half_toggle():
    u = {"higher_barrier": "+0.12", "lower_barrier": "-0.12", "half_barrier_enabled": True}

    assert _get_unchain_visible_barrier(u, "HIGHER", "t") == "+0.06"
    assert _get_unchain_visible_barrier(u, "LOWER", "t") == "-0.06"


def test_handle_on_message_error_cleans_failed_digit_buy_req_meta(monkeypatch):
    emitted = []
    cid = "cid-buy-error"
    state = {
        "ws_nonce": "nonce-1",
        "req_meta": {101: {"profile": "KOOLKID", "type": "OVER", "stake": 1.0}},
        "strategies": {},
    }
    server.clients[cid] = state
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))

    try:
        server.handle_on_message(
            cid,
            None,
            json.dumps({"error": {"message": "Buy rejected"}, "req_id": 101}),
            "nonce-1",
        )
    finally:
        server.clients.pop(cid, None)

    assert state["req_meta"] == {}
    assert any(event == "api_error" for event, _payload, _room in emitted)


def test_handle_on_message_error_clears_failed_unchain_pending_request(monkeypatch):
    emitted = []
    cid = "cid-unchain-buy-error"
    strat = server.UnchainStrategy()
    strat.pending_trade_request = True
    strat.pending_trade_mode = "AUTO"
    strat.pending_trade_exit_ticks = 5
    strat.pending_trade_stake = 2.5
    state = {
        "ws_nonce": "nonce-2",
        "req_meta": {202: {"profile": "UNCHAIN", "type": "ACCU", "stake": 2.5}},
        "strategies": {"UNCHAIN": strat},
    }
    server.clients[cid] = state
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))

    try:
        server.handle_on_message(
            cid,
            None,
            json.dumps({"error": {"message": "Insufficient funds"}, "req_id": 202}),
            "nonce-2",
        )
    finally:
        server.clients.pop(cid, None)

    assert state["req_meta"] == {}
    assert strat.pending_trade_request is False
    assert strat.pending_trade_mode is None
    assert strat.pending_trade_exit_ticks is None
    assert strat.pending_trade_stake is None
    assert any(event == "api_error" for event, _payload, _room in emitted)


def test_unchain_zero_profit_counts_as_loss():
    strat = server.UnchainStrategy()

    strat.on_contract({"profit": 0, "buy_price": 1.0, "contract_id": 1}, 10.0)

    assert strat.total_wins == 0
    assert strat.total_losses == 1
    assert strat.last_result == "LOSS"


def test_serialize_profile_trade_history_entry_zero_profit_defaults_to_loss():
    snapshot = _serialize_profile_trade_history_entry("UNCHAIN", {"profit": 0.0}, 0)

    assert snapshot["result"] == "LOSS"


def test_set_risk_controls_can_target_explicit_profile(monkeypatch):
    class Recorder:
        def __init__(self):
            self.calls = []

        def set_risk_controls(self, tp=0.0, sl=0.0, auto_sl=True):
            self.calls.append({"tp": tp, "sl": sl, "auto_sl": auto_sl})

    koolkid = Recorder()
    jokerjoe = Recorder()
    state = {
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": koolkid, "JOKERJOE": jokerjoe},
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-risk", state))

    with server.app.test_client() as client:
        res = client.post(
            "/set_risk_controls",
            json={"profile": "JOKERJOE", "tp": 5, "sl": 3, "auto_sl": False},
        )

    assert res.status_code == 200
    assert koolkid.calls == []
    assert jokerjoe.calls == [{"tp": 5.0, "sl": 3.0, "auto_sl": False}]


def test_clear_profile_history_resets_unchain_runtime_state(monkeypatch):
    strat = server.UnchainStrategy()
    strat.trade_history = [{"result": "WIN"}]
    strat.total_wins = 3
    strat.total_losses = 2
    strat.session_profit = 4.5
    strat.pending_trade_request = True
    strat.pending_trade_mode = "AUTO"
    strat.pending_trade_exit_ticks = 5
    strat.pending_trade_stake = 2.0
    strat.active_contract_id = "123"
    strat.active_contract_open = True
    strat.risk_block_reason = "TP hit (+4.50)"

    state = {"active_profile": "UNCHAIN", "strategies": {"UNCHAIN": strat}}
    u = server._ensure_unchain_hl_state(state)
    u["stats"] = {"wins": 5, "losses": 4, "net_pnl": 3.0}
    u["last_result"] = "LOSS"
    u["last_action"] = "Blocked"
    u["risk_block_reason"] = "Blocked"
    u["active_contracts"] = {"abc": {"status": "OPEN"}}
    u["auto_cycle_losses"] = 2
    u["auto_last_cycle_had_loss"] = True
    u["auto_pair_active"] = True
    u["auto_both_pair_active"] = True

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-clear", state))
    monkeypatch.setattr(server, "send_stats_update", lambda _cid: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    with server.app.test_client() as client:
        res = client.post("/clear_profile_history", json={"profile": "UNCHAIN"})

    assert res.status_code == 200
    assert strat.trade_history == []
    assert strat.total_wins == 0
    assert strat.total_losses == 0
    assert strat.session_profit == 0.0
    assert strat.pending_trade_request is False
    assert strat.active_contract_id is None
    assert strat.risk_block_reason is None
    assert u["stats"] == {"wins": 0, "losses": 0, "net_pnl": 0.0}
    assert u["active_contracts"] == {}
    assert u["auto_cycle_losses"] == 0
    assert u["auto_last_cycle_had_loss"] is False
    assert u["auto_pair_active"] is False
    assert u["auto_both_pair_active"] is False


def test_ensure_unchain_state_keeps_standard_default_barriers():
    state = {"current_symbol": "1HZ75V"}

    u = _ensure_unchain_hl_state(state)

    assert u["higher_barrier"] == "+0.12"
    assert u["lower_barrier"] == "-0.12"


def test_format_unchain_market_default_barrier_uses_relative_deriv_value():
    assert _format_unchain_market_default_barrier("+0.33", "HIGHER") == "+0.33"
    assert _format_unchain_market_default_barrier("+0.33", "LOWER") == "-0.33"


def test_format_unchain_market_default_barrier_truncates_to_two_decimals():
    assert _format_unchain_market_default_barrier("8.0487", "HIGHER") == "+8.04"
    assert _format_unchain_market_default_barrier("8.0487", "LOWER") == "-8.04"
    assert _format_unchain_market_default_barrier("0.1799", "HIGHER") == "+0.17"
    assert _format_unchain_market_default_barrier("0.1799", "LOWER") == "-0.17"


def test_apply_unchain_market_default_barriers_updates_main_and_koolkid_setup(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_75",
        "unchain_hl": {
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "higher_stake": 1.0,
            "duration": 5,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(
        server,
        "_fetch_unchain_market_default_barrier",
        lambda *args, **kwargs: ("+0.33", None),
    )

    ok, info = _apply_unchain_market_default_barriers(state, "R_75")

    assert ok is True
    assert info == "+0.33 / -0.33"
    assert state["unchain_hl"]["higher_barrier"] == "+0.33"
    assert state["unchain_hl"]["lower_barrier"] == "-0.33"
    assert state["unchain_hl"]["koolkid_higher_barrier"] == "+0.33"
    assert state["unchain_hl"]["koolkid_lower_barrier"] == "-0.33"
    assert state["unchain_hl"]["market_default_symbol"] == "R_75"
    assert state["unchain_hl"]["market_default_key"] == "R_75|5|T"


def test_apply_unchain_market_default_barriers_reverses_koolkid_barriers_when_enabled(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_75",
        "unchain_hl": {
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "higher_stake": 1.0,
            "duration": 5,
            "duration_unit": "t",
            "koolkid_reversal_enabled": True,
        },
    }

    monkeypatch.setattr(
        server,
        "_fetch_unchain_market_default_barrier",
        lambda *args, **kwargs: ("+0.33", None),
    )

    ok, info = _apply_unchain_market_default_barriers(state, "R_75")

    assert ok is True
    assert info == "+0.33 / -0.33"
    assert state["unchain_hl"]["higher_barrier"] == "+0.33"
    assert state["unchain_hl"]["lower_barrier"] == "-0.33"
    assert state["unchain_hl"]["koolkid_higher_barrier"] == "-0.33"
    assert state["unchain_hl"]["koolkid_lower_barrier"] == "+0.33"
    assert state["unchain_hl"]["market_default_symbol"] == "R_75"
    assert state["unchain_hl"]["market_default_key"] == "R_75|5|T"


def test_sync_unchain_market_default_barriers_only_refreshes_unsynced_symbol(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_10",
        "unchain_hl": {
            "higher_barrier": "+0.12",
            "lower_barrier": "-0.12",
            "koolkid_higher_barrier": "+0.12",
            "koolkid_lower_barrier": "-0.12",
            "duration": 5,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(
        server,
        "_fetch_unchain_market_default_barrier",
        lambda *args, **kwargs: ("+0.33", None),
    )

    changed, info = server._sync_unchain_market_default_barriers(state, force=False)

    assert changed is True
    assert info == "+0.33 / -0.33"
    assert state["unchain_hl"]["higher_barrier"] == "+0.33"
    assert state["unchain_hl"]["market_default_symbol"] == "R_10"
    assert state["unchain_hl"]["market_default_key"] == "R_10|5|T"

    state["unchain_hl"]["higher_barrier"] = "+9.99"
    state["unchain_hl"]["lower_barrier"] = "-9.99"

    changed, info = server._sync_unchain_market_default_barriers(state, force=False)

    assert changed is False
    assert info == "Already synced"
    assert state["unchain_hl"]["higher_barrier"] == "+9.99"
    assert state["unchain_hl"]["lower_barrier"] == "-9.99"


def test_sync_unchain_market_default_barriers_refreshes_when_duration_key_changes(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_10",
        "unchain_hl": {
            "higher_barrier": "+0.33",
            "lower_barrier": "-0.33",
            "market_default_symbol": "R_10",
            "market_default_key": "R_10|5|T",
            "duration": 10,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(
        server,
        "_fetch_unchain_market_default_barrier",
        lambda *args, **kwargs: ("+0.55", None),
    )

    changed, info = server._sync_unchain_market_default_barriers(state, force=False)

    assert changed is True
    assert info == "+0.55 / -0.55"
    assert state["unchain_hl"]["higher_barrier"] == "+0.55"
    assert state["unchain_hl"]["lower_barrier"] == "-0.55"
    assert state["unchain_hl"]["market_default_key"] == "R_10|10|T"


def test_sync_unchain_market_default_barriers_force_refreshes_on_login(monkeypatch):
    state = {
        "ws_connected": True,
        "ws": object(),
        "current_symbol": "R_10",
        "unchain_hl": {
            "higher_barrier": "+9.99",
            "lower_barrier": "-9.99",
            "market_default_symbol": "R_10",
            "duration": 5,
            "duration_unit": "t",
        },
    }

    monkeypatch.setattr(
        server,
        "_fetch_unchain_market_default_barrier",
        lambda *args, **kwargs: ("+0.33", None),
    )

    changed, info = server._sync_unchain_market_default_barriers(state, force=True)

    assert changed is True
    assert info == "+0.33 / -0.33"
    assert state["unchain_hl"]["higher_barrier"] == "+0.33"
    assert state["unchain_hl"]["lower_barrier"] == "-0.33"


def test_serialize_profile_trade_history_entry_preserves_real_contract_id():
    entry = {
        "contract_id": 123456,
        "time": "10:00:00",
        "result": "WIN",
        "profit": 1.25,
        "stake": 1.0,
        "symbol": "R_10",
        "type": "DIFFERS",
    }

    snapshot = _serialize_profile_trade_history_entry("JOKERJOE", entry, 0)

    assert snapshot["profile"] == "JOKERJOE"
    assert snapshot["contract_id"] == "123456"
    assert snapshot["result"] == "WIN"
    assert snapshot["pending"] is False


def test_get_profile_trade_history_snapshot_builds_stable_ids_for_entries_without_contract_id():
    trade_entry = {
        "time": "10:15:00",
        "result": "LOSS",
        "profit": -1.0,
        "stake": 1.0,
        "symbol": "R_25",
        "type": "OVER",
    }
    strat = SimpleNamespace(trade_history=[trade_entry])
    state = {"strategies": {"KOOLKID": strat}}

    first = _get_profile_trade_history_snapshot(state, "KOOLKID")
    second = _get_profile_trade_history_snapshot(state, "KOOLKID")

    first_item = first["KOOLKID"][0]
    second_item = second["KOOLKID"][0]
    assert first_item["contract_id"].startswith("SNAPSHOT-KOOLKID-")
    assert first_item["contract_id"] == second_item["contract_id"]
    assert first_item["result"] == "LOSS"


def test_process_contract_forces_settled_result_off_pending_labels(monkeypatch):
    emitted = []

    class DummyStrategy:
        def __init__(self):
            self.last_trade_entry = {}

        def on_contract(self, contract, balance):
            self.last_trade_entry = {
                "time": "10:00:00",
                "result": "PENDING",
                "profit": round(float(contract.get("profit", 0) or 0), 2),
                "symbol": contract.get("underlying", ""),
            }

        def get_last_trade_entry(self):
            return self.last_trade_entry

    state = {
        "balance": 100.0,
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": DummyStrategy()},
        "contract_meta": {
            12345: {
                "profile": "KOOLKID",
                "type": "OVER",
                "stake": 1.0,
                "symbol": "R_10",
                "time": "09:59:00",
                "duration": 5,
                "duration_unit": "t",
            }
        },
    }

    monkeypatch.setitem(server.clients, "test-client", state)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda client_id: None)

    try:
        process_contract(
            "test-client",
            {
                "contract_id": 12345,
                "status": "sold",
                "profit": 0.6,
                "is_sold": True,
                "underlying": "R_10",
            },
        )
    finally:
        server.clients.pop("test-client", None)

    trade_events = [payload for event, payload, _room in emitted if event == "trade_result"]
    assert trade_events
    assert trade_events[-1]["contract_id"] == 12345
    assert trade_events[-1]["result"] == "WIN"
    assert trade_events[-1]["status"] == "sold"


def test_process_contract_extracts_exit_digit_from_current_spot_display_value(monkeypatch):
    emitted = []

    class DummyStrategy:
        def __init__(self):
            self.last_trade_entry = {}

        def on_contract(self, contract, balance):
            self.last_trade_entry = {
                "time": "10:00:00",
                "result": "WIN" if float(contract.get("profit", 0) or 0) > 0 else "LOSS",
                "profit": round(float(contract.get("profit", 0) or 0), 2),
                "symbol": contract.get("underlying", ""),
            }

        def get_last_trade_entry(self):
            return self.last_trade_entry

    state = {
        "balance": 100.0,
        "active_profile": "JOKERJOE",
        "strategies": {"JOKERJOE": DummyStrategy()},
        "contract_meta": {
            54321: {
                "profile": "JOKERJOE",
                "type": "DIFFERS",
                "stake": 1.0,
                "symbol": "R_10",
                "time": "09:59:00",
                "duration": 5,
                "duration_unit": "t",
            }
        },
    }

    monkeypatch.setitem(server.clients, "test-exit-digit", state)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda client_id: None)

    try:
        process_contract(
            "test-exit-digit",
            {
                "contract_id": 54321,
                "status": "sold",
                "profit": 0.6,
                "is_sold": True,
                "underlying": "R_10",
                "current_spot_display_value": "9744.54",
            },
        )
    finally:
        server.clients.pop("test-exit-digit", None)

    trade_events = [payload for event, payload, _room in emitted if event == "trade_result"]
    assert trade_events
    assert trade_events[-1]["contract_id"] == 54321
    assert trade_events[-1]["exit_digit"] == 4


def test_process_contract_does_not_double_apply_profit_after_fresh_balance_update(monkeypatch):
    emitted = []

    class DummyStrategy:
        def __init__(self):
            self.last_trade_entry = {}

        def on_contract(self, contract, balance):
            self.last_trade_entry = {
                "time": "10:00:00",
                "result": "LOSS",
                "profit": round(float(contract.get("profit", 0) or 0), 2),
                "symbol": contract.get("underlying", ""),
                "balance_seen": balance,
            }

        def get_last_trade_entry(self):
            return self.last_trade_entry

    state = {
        "balance": 100.0,
        "balance_updated_at": time.time(),
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": DummyStrategy()},
        "contract_meta": {
            24680: {
                "profile": "KOOLKID",
                "type": "OVER",
                "stake": 1.0,
                "symbol": "R_10",
                "time": "09:59:00",
                "duration": 5,
                "duration_unit": "t",
            }
        },
    }

    monkeypatch.setitem(server.clients, "test-fresh-balance", state)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda client_id: None)

    try:
        process_contract(
            "test-fresh-balance",
            {
                "contract_id": 24680,
                "status": "sold",
                "profit": -5.0,
                "is_sold": True,
                "underlying": "R_10",
            },
        )
    finally:
        server.clients.pop("test-fresh-balance", None)

    assert state["balance"] == pytest.approx(100.0)
    trade_events = [payload for event, payload, _room in emitted if event == "trade_result"]
    assert trade_events
    assert trade_events[-1]["profit"] == -5.0


def test_process_contract_ignores_duplicate_non_unchain_settlement(monkeypatch):
    emitted = []

    class DummyStrategy:
        def __init__(self):
            self.calls = 0
            self.last_trade_entry = {}

        def on_contract(self, contract, balance):
            self.calls += 1
            self.last_trade_entry = {
                "time": "10:00:00",
                "result": "LOSS",
                "profit": round(float(contract.get("profit", 0) or 0), 2),
                "symbol": contract.get("underlying", ""),
                "balance_seen": balance,
            }

        def get_last_trade_entry(self):
            return self.last_trade_entry

    strategy = DummyStrategy()
    state = {
        "balance": 100.0,
        "balance_updated_at": 0.0,
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": strategy},
        "contract_meta": {
            77777: {
                "profile": "KOOLKID",
                "type": "OVER",
                "stake": 1.0,
                "symbol": "R_10",
                "time": "09:59:00",
                "duration": 5,
                "duration_unit": "t",
            }
        },
    }

    monkeypatch.setitem(server.clients, "test-duplicate-regular", state)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "send_stats_update", lambda client_id: None)

    contract = {
        "contract_id": 77777,
        "status": "sold",
        "profit": -4.0,
        "is_sold": True,
        "underlying": "R_10",
    }

    try:
        process_contract("test-duplicate-regular", contract)
        process_contract("test-duplicate-regular", contract)
    finally:
        server.clients.pop("test-duplicate-regular", None)

    assert strategy.calls == 1
    assert state["balance"] == pytest.approx(96.0)
    trade_events = [payload for event, payload, _room in emitted if event == "trade_result"]
    assert len(trade_events) == 1


def test_send_buy_allows_stake_equal_to_rounded_balance():
    class DummyWs:
        def __init__(self):
            self.sent = []

        def send(self, payload):
            self.sent.append(json.loads(payload))

    cid = "test-koolkid-send-buy-rounded"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state["ws_connected"] = True
    state["ws"] = DummyWs()
    state["balance"] = 99.995
    state["active_profile"] = "KOOLKID"

    try:
        ok, msg = server.send_buy(cid, "OVER", 100.0, "R_10", 5)
    finally:
        server.clients.pop(cid, None)

    assert ok is True
    assert msg == "Trade sent"
    assert len(state["ws"].sent) == 1


def test_send_unchain_hl_trade_uses_half_barrier_setting(monkeypatch):
    sent = []

    class DummyWs:
        def send(self, payload):
            sent.append(json.loads(payload))

    state = {
        "ws_connected": True,
        "ws": DummyWs(),
        "req_meta": {},
        "unchain_hl": {"half_barrier_enabled": True},
    }
    server.clients["test-half-barrier"] = state
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)

    try:
        ok, msg = _send_unchain_hl_trade(
            "test-half-barrier",
            side="HIGHER",
            stake=1.0,
            symbol="R_25",
            barrier="+0.12",
            duration=5,
            duration_unit="t",
        )
    finally:
        server.clients.pop("test-half-barrier", None)

    assert ok is True
    assert "sent" in msg.lower()
    assert sent
    assert sent[0]["parameters"]["barrier"] == "+0.06"


def test_send_unchain_hl_trade_can_skip_saved_half_toggle(monkeypatch):
    sent = []

    class DummyWs:
        def send(self, payload):
            sent.append(json.loads(payload))

    state = {
        "ws_connected": True,
        "ws": DummyWs(),
        "req_meta": {},
        "unchain_hl": {"half_barrier_enabled": True},
    }
    server.clients["test-skip-half-barrier"] = state
    monkeypatch.setattr(server, "_check_unchain_hl_risk_block", lambda state: None)

    try:
        ok, msg = _send_unchain_hl_trade(
            "test-skip-half-barrier",
            side="LOWER",
            stake=1.0,
            symbol="R_25",
            barrier="-0.06",
            duration=5,
            duration_unit="t",
            respect_half_barrier_toggle=False,
        )
    finally:
        server.clients.pop("test-skip-half-barrier", None)

    assert ok is True
    assert "sent" in msg.lower()
    assert sent
    assert sent[0]["parameters"]["barrier"] == "-0.06"
