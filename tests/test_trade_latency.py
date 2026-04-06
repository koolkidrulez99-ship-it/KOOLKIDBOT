import json
import threading
import time

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

