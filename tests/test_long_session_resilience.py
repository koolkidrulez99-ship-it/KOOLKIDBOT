import json
import threading
from pathlib import Path
from types import SimpleNamespace

import server
from bot_modules.trade_history import (
    PROFILE_TRADE_HISTORY_LIMIT,
    append_bounded_trade_history,
    get_profile_trade_history_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def test_bounded_history_keeps_latest_500_and_updates_duplicate_contract():
    history = []
    for index in range(800):
        append_bounded_trade_history(history, {"contract_id": str(index), "profit": index})

    assert len(history) == PROFILE_TRADE_HISTORY_LIMIT == 500
    assert history[0]["contract_id"] == "300"
    assert history[-1]["contract_id"] == "799"

    append_bounded_trade_history(history, {"contract_id": "799", "profit": 999})
    assert len(history) == 500
    assert history[-1]["profit"] == 999


def test_snapshot_never_serializes_unbounded_strategy_history():
    strategy = SimpleNamespace(
        trade_history=[{"contract_id": str(index), "profit": 1} for index in range(900)]
    )
    snapshot = get_profile_trade_history_snapshot({"strategies": {"KOOLKID": strategy}}, "KOOLKID")

    assert len(snapshot["KOOLKID"]) == PROFILE_TRADE_HISTORY_LIMIT
    assert snapshot["KOOLKID"][0]["contract_id"] == "400"
    assert snapshot["KOOLKID"][-1]["contract_id"] == "899"


def test_deriv_messages_extend_background_runtime_lease():
    state = {"api_token": "secret", "last_seen": 100.0, "ws_last_message_at": 900.0}
    assert server._client_runtime_last_activity(state) == 900.0
    assert server._client_runtime_last_activity({"last_seen": 100.0, "ws_last_message_at": 900.0}) == 100.0


def test_connected_health_check_self_heals_tick_stream(monkeypatch):
    calls = []
    state = {"api_token": "secret", "ws_connected": True, "ws": object()}
    monkeypatch.setattr(
        server,
        "_get_tick_stream_health",
        lambda cid, current, **kwargs: calls.append((cid, current, kwargs)) or {},
    )

    assert server._run_websocket_health_check("client", state, now_ts=100.0)
    assert calls == [("client", state, {"self_heal": True, "allow_reconnect": True})]


def test_disconnected_health_check_schedules_bounded_reconnect(monkeypatch):
    calls = []
    state = {
        "api_token": "secret",
        "ws_connected": False,
        "ws_reconnect_pending": False,
        "ws_connect_started_at": 0.0,
        "ws_reconnect_attempts": 20,
        "ws_nonce": 7,
    }
    monkeypatch.setattr(server, "_check_ws_connect_timeout", lambda *args: None)
    monkeypatch.setattr(server.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(
        server,
        "_schedule_ws_reconnect",
        lambda cid, nonce, delay_sec: calls.append((cid, nonce, delay_sec)) or True,
    )

    assert server._run_websocket_health_check("client", state, now_ts=100.0)
    assert calls == [("client", 7, server.WS_RECONNECT_MAX_DELAY_SEC)]


def test_pat_close_preserves_account_display_while_reconnecting(monkeypatch):
    emitted = []
    reconnects = []
    state = {
        "api_token": "pat_secret",
        "api_token_type": "pat",
        "loginid": "CR123",
        "ws_nonce": 4,
        "ws_stop_event": threading.Event(),
        "ws_connected": True,
    }
    monkeypatch.setattr(server, "clients", {"client": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, **kwargs: emitted.append((event, payload)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=2.0: reconnects.append((cid, nonce, delay_sec)) or True)

    server.handle_on_close("client", None, 1006, "network interruption", 4)

    status = next(payload for event, payload in emitted if event == "connection_status")
    assert status["reconnecting"] is True
    assert status["preserve_session_display"] is True
    assert status["loginid"] == "CR123"
    assert reconnects == [("client", 4, 2.0)]


def test_pat_ping_timeout_default_is_tolerant():
    assert server.DERIV_WS_PING_TIMEOUT_SEC >= 20


def test_reconnect_restores_each_pending_contract_once():
    sent = []
    ws = SimpleNamespace(send=lambda payload: sent.append(json.loads(payload)))
    state = {
        "contract_meta": {"123": {}, 123: {}, "456": {}},
        "human_pending_contracts": {"456": {}, "789": {}},
        "unchain_hl": {"active_contracts": {"789": {}, "900": {}}},
    }

    assert server._restore_pending_contract_subscriptions("client", state, ws) == 4
    assert {str(item["contract_id"]) for item in sent} == {"123", "456", "789", "900"}
    assert all(item["subscribe"] == 1 for item in sent)


def test_busy_auto_dispatch_coalesces_one_follow_up(monkeypatch):
    workers = []
    timers = []
    executions = []
    state = {
        "active_profile": "KOOLKID",
        "current_symbol": "R_25",
        "ws_nonce": 1,
        "ws_connected": True,
    }
    monkeypatch.setattr(server, "clients", {"client": state})
    monkeypatch.setattr(
        server.threading,
        "Thread",
        lambda target, **_kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    monkeypatch.setattr(
        server.threading,
        "Timer",
        lambda _delay, target: SimpleNamespace(
            daemon=False,
            cancel=lambda: None,
            start=lambda: timers.append(target),
        ),
    )
    monkeypatch.setattr(server, "run_auto_trade", lambda *_args: executions.append("run"))

    assert server._schedule_profile_auto_trade("client", state)
    assert not server._schedule_profile_auto_trade("client", state)
    workers.pop(0)()
    timers.pop(0)()
    assert len(workers) == 1
    workers.pop(0)()
    assert executions == ["run", "run"]
    assert not state["_profile_auto_dispatch_lock"].locked()


def test_frontend_long_session_history_guards_are_present():
    source = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "const TRADE_STORE_MAX_ITEMS = 500;" in source
    assert 'document.hidden) return false' not in source
    assert 'upsertTradeInStore(Object.assign({}, trade, { profile }), { persist: false })' in source
    assert "Math.min(TRADE_STORE_MAX_ITEMS, Number(expectedSettledCount || 0))" in source
