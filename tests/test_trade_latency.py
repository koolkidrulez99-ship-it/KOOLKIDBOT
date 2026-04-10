import json
import threading
import time

import pytest

import server


class _InlineThread:
    def __init__(self, target=None, args=None, kwargs=None, **_rest):
        self._target = target
        self._args = args or ()
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


class _DummyWs:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, payload):
        self.messages.append(json.loads(payload))

    def close(self):
        self.closed = True


class _BrokenSendWs:
    def send(self, _payload):
        raise RuntimeError("send failed")


class _ExplodingWebSocketApp:
    def __init__(self, *_args, **_kwargs):
        pass

    def run_forever(self, **_kwargs):
        raise RuntimeError("run_forever failed")

    def close(self):
        return None


def test_schedule_contract_open_refresh_requests_one_shot_status(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {},
    }
    monkeypatch.setattr(server, "clients", {"cid-fast": state})
    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    monkeypatch.setattr(server.time, "sleep", lambda *_args, **_kwargs: None)

    ok = server._schedule_contract_open_refresh("cid-fast", "nonce-1", "12345", delays=(0.01,))

    assert ok is True
    assert ws.messages == [{"proposal_open_contract": 1, "contract_id": 12345}]


def test_schedule_contract_open_refresh_skips_when_subscription_already_exists(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {"12345": "sub-1"},
    }
    monkeypatch.setattr(server, "clients", {"cid-fast": state})
    monkeypatch.setattr(server.threading, "Thread", _InlineThread)
    monkeypatch.setattr(server.time, "sleep", lambda *_args, **_kwargs: None)

    ok = server._schedule_contract_open_refresh("cid-fast", "nonce-1", "12345", delays=(0.01,))

    assert ok is True
    assert ws.messages == []


def test_request_open_contract_subscribes_only_once_until_cleared():
    ws = _DummyWs()
    state = {
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {},
    }

    first = server._request_open_contract(state, "12345", subscribe=True, ws=ws)
    second = server._request_open_contract(state, "12345", subscribe=True, ws=ws)

    assert first is True
    assert second is True
    assert ws.messages == [{"proposal_open_contract": 1, "contract_id": "12345", "subscribe": 1}]
    assert state["open_contract_subs"]["12345"] == "__pending__"


def test_set_token_logs_connect_request_and_thread_start(monkeypatch):
    events = []
    state = {
        "active_profile": "KOOLKID",
        "ws_stop_event": threading.Event(),
        "profile_budgets": server._new_profile_budget_map(),
    }

    class _ThreadStub:
        def __init__(self, target=None, args=None, kwargs=None, **_rest):
            self.target = target
            self.args = args or ()
            self.kwargs = kwargs or {}
            self.name = "ws-thread-test"

        def is_alive(self):
            return False

        def start(self):
            return None

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-connect", state))
    monkeypatch.setattr(server, "_persist_trade_runtime_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server.threading, "Thread", _ThreadStub)
    monkeypatch.setattr(server, "_log_runtime_debug", lambda event, client_id=None, **fields: events.append((event, client_id, fields)))

    with server.app.test_request_context("/set_token", method="POST", json={"token": "abc123"}):
        response = server.set_token()

    assert response.status_code == 200
    assert any(event == "api_connect_request_received" and client_id == "cid-connect" for event, client_id, _fields in events)
    assert any(event == "deriv_websocket_thread_starting" and client_id == "cid-connect" for event, client_id, _fields in events)


def test_start_ws_for_client_logs_hidden_run_forever_failure(monkeypatch):
    events = []
    emitted = []
    state = {
        "ws_nonce": 0,
        "ws_stop_event": threading.Event(),
        "ws": None,
        "api_token": "token",
        "balance": 0.0,
        "profile_budgets": server._new_profile_budget_map(),
    }
    monkeypatch.setattr(server, "clients", {"cid-thread": state})
    monkeypatch.setattr(server.websocket, "WebSocketApp", _ExplodingWebSocketApp)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_log_runtime_debug", lambda event, client_id=None, **fields: events.append((event, client_id, fields)))

    server.start_ws_for_client("cid-thread")

    assert any(event == "deriv_websocket_thread_started" for event, _client_id, _fields in events)
    assert any(event == "deriv_websocket_thread_exception" and fields.get("error") == "RuntimeError('run_forever failed')" for event, _client_id, fields in events)
    assert any(event == "connection_status" and payload.get("connected") is False for event, payload, _room in emitted)
    assert any(event == "api_error" for event, _payload, _room in emitted)


def test_handle_on_open_logs_authorize_send_failure(monkeypatch):
    events = []
    state = {
        "ws_nonce": "nonce-open",
        "api_token": "token-123",
    }
    monkeypatch.setattr(server, "clients", {"cid-open": state})
    monkeypatch.setattr(server, "_log_runtime_debug", lambda event, client_id=None, **fields: events.append((event, client_id, fields)))

    with pytest.raises(RuntimeError, match="send failed"):
        server.handle_on_open("cid-open", _BrokenSendWs(), "nonce-open")

    assert any(event == "deriv_websocket_opened" for event, _client_id, _fields in events)
    assert any(event == "authorize_sent" for event, _client_id, _fields in events)
    assert any(event == "authorize_failure" and fields.get("stage") == "send" for event, _client_id, fields in events)


def test_handle_on_message_logs_authorize_success_and_balance_subscribe(monkeypatch):
    events = []
    emitted = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-msg",
        "session_start_balance": None,
        "profile_budgets": server._new_profile_budget_map(),
        "strategies": {},
        "active_profile": "KOOLKID",
        "balance": 0.0,
    }
    monkeypatch.setattr(server, "clients", {"cid-msg": state})
    monkeypatch.setattr(server, "_log_runtime_debug", lambda event, client_id=None, **fields: events.append((event, client_id, fields)))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "emit_profile_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "request_human_seed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_resume_restored_mutant_auto", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_maybe_start_trade_reconcile", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        server,
        "build_post_authorize_requests",
        lambda _state, include_balance=True: [
            {"balance": 1, "subscribe": 1},
            {"ticks": "R_10", "subscribe": 1},
        ],
    )

    server.handle_on_message(
        "cid-msg",
        ws,
        json.dumps({"authorize": {"loginid": "CR111", "balance": 42.5}}),
        "nonce-msg",
    )

    assert any(event == "authorize_success" for event, _client_id, _fields in events)
    assert any(event == "api_connected_state_emitted" for event, _client_id, _fields in events)
    assert any(event == "balance_subscribe_sent" for event, _client_id, _fields in events)
    assert any(event == "tick_subscribe_sent" and fields.get("symbol") == "R_10" for event, _client_id, fields in events)
    assert ws.messages == [{"balance": 1, "subscribe": 1}, {"ticks": "R_10", "subscribe": 1}]


def test_forget_pending_open_contract_subscription_clears_without_forget_send():
    ws = _DummyWs()
    state = {
        "ws_connected": True,
        "ws": ws,
        "open_contract_subs": {"12345": "__pending__"},
    }

    cleared = server._forget_unchain_open_contract_subscription(state, "12345")

    assert cleared is True
    assert ws.messages == []
    assert state["open_contract_subs"] == {}


def test_send_buy_marks_stale_socket_unhealthy_and_requests_reconnect(monkeypatch):
    emitted = []
    reconnects = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-1",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws_last_message_at": time.time() - (server.DERIV_WS_STALE_TIMEOUT_SEC + 5),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "req_meta": {},
        "balance": 100.0,
        "strategies": {"KOOLKID": None},
        "loginid": "CR123",
    }
    monkeypatch.setattr(server, "clients", {"cid-stale": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    ok, msg = server.send_buy("cid-stale", "OVER", 1.0, "R_10", 5)

    assert ok is False
    assert "stale" in msg.lower() or "reconnecting" in msg.lower()
    assert state["ws_connected"] is False
    assert ws.closed is True
    assert reconnects == [("cid-stale", "nonce-1", 0.25)]
    assert any(event == "connection_status" and payload.get("connected") is False for event, payload, _room in emitted)


def test_api_connection_status_reports_false_for_stale_socket(monkeypatch):
    reconnects = []
    emitted = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-2",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws_last_message_at": time.time() - (server.DERIV_WS_STALE_TIMEOUT_SEC + 5),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "balance": 55.0,
        "profile_budgets": server._new_profile_budget_map(),
        "active_profile": "KOOLKID",
        "session_start_balance": None,
        "loginid": "CR456",
    }
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-status", state))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    with server.app.test_request_context("/api_connection_status"):
        response = server.api_connection_status()

    data = response.get_json()
    assert data["connected"] is False
    assert state["ws_connected"] is False
    assert reconnects == [("cid-status", "nonce-2", 0.25)]
    assert any(event == "connection_status" and payload.get("connected") is False for event, payload, _room in emitted)


def test_api_connection_status_reconnects_when_authorize_stays_pending_too_long(monkeypatch):
    reconnects = []
    emitted = []
    ws = _DummyWs()
    state = {
        "ws_nonce": "nonce-auth",
        "ws_connected": False,
        "ws_transport_connected": True,
        "ws_connect_started_at": time.time() - 10,
        "ws_authorize_deadline_at": time.time() - 1,
        "ws_last_message_at": time.time(),
        "ws": ws,
        "api_token": "token",
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "balance": 55.0,
        "profile_budgets": server._new_profile_budget_map(),
        "active_profile": "KOOLKID",
        "session_start_balance": None,
        "loginid": "UNKNOWN",
    }
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-auth", state))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))
    monkeypatch.setattr(server, "_schedule_ws_reconnect", lambda cid, nonce, delay_sec=0.25: reconnects.append((cid, nonce, delay_sec)) or True)

    with server.app.test_request_context("/api_connection_status"):
        response = server.api_connection_status()

    data = response.get_json()
    assert data["connected"] is False
    assert state["ws_transport_connected"] is False
    assert ws.closed is True
    assert reconnects == [("cid-auth", "nonce-auth", 0.25)]
    assert any(event == "connection_status" and payload.get("connected") is False for event, payload, _room in emitted)


def test_batch_trade_sleep_seconds_gives_turbo_a_much_faster_lane():
    normal = server._batch_trade_sleep_seconds({}, 0.04)
    turbo = server._batch_trade_sleep_seconds({"turbo": True}, 0.04)

    assert normal >= 0.08
    assert turbo == 0.002
    assert turbo < normal


def test_profile_history_snapshot_includes_live_confirmed_execution_record():
    client_id = "cid-history-live"
    if client_id in server.clients:
        server.clients.pop(client_id, None)
    server.init_client(client_id)
    state = server.clients[client_id]

    meta = {
        "profile": "KOOLKID",
        "type": "OVER",
        "barrier": 5,
        "stake": 1.0,
        "symbol": "R_25",
        "time": "10:00:00",
        "duration": 1,
        "duration_unit": "t",
        "mode": "MANUAL",
    }

    server._register_trade_execution_submission(client_id, state, "req-live-1", meta)
    server._mark_trade_execution_buy_confirmed(client_id, state, "req-live-1", "999", meta=meta)

    snapshot = server._get_profile_trade_history_snapshot(state, "KOOLKID")
    items = snapshot["KOOLKID"]

    assert any(item.get("contract_id") == "999" for item in items)
    live_item = next(item for item in items if item.get("contract_id") == "999")
    assert live_item["pending"] is True
    assert live_item["result"] == "PENDING"
    assert live_item["pending_state"] == server.TRADE_STATE_CONFIRMED
