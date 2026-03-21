import json

import pytest
from types import SimpleNamespace

import server
from server import (
    _ensure_unchain_hl_state,
    _decorate_unchain_active_entry_countdown,
    _format_unchain_barrier,
    _half_unchain_barrier,
    _is_contract_settled_fast,
    _send_unchain_hl_trade,
    _upsert_unchain_active_contract,
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


def test_ensure_unchain_state_restores_v75_default_barriers():
    state = {"current_symbol": "1HZ75V"}

    u = _ensure_unchain_hl_state(state)

    assert u["higher_barrier"] == "+3.88"
    assert u["lower_barrier"] == "-3.88"


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
