import json

import pytest
from types import SimpleNamespace

import server
from server import (
    _apply_unchain_market_default_barriers,
    _ensure_unchain_hl_state,
    _decorate_unchain_active_entry_countdown,
    _format_unchain_barrier,
    _format_unchain_market_default_barrier,
    _get_unchain_visible_barrier,
    _half_unchain_barrier,
    _is_contract_settled_fast,
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
