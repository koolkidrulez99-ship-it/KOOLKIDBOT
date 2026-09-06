import json
import threading
import time

import server


class DummyWs:
    def __init__(self):
        self.messages = []
        self.closed = False

    def send(self, payload):
        self.messages.append(json.loads(payload))

    def close(self):
        self.closed = True


def _base_state(api_token_type="legacy"):
    return {
        "ws_nonce": 1,
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws_last_message_at": time.time(),
        "ws": DummyWs(),
        "api_token": "legacy-token" if api_token_type == "legacy" else "pat_test",
        "api_token_type": api_token_type,
        "ws_reconnect_pending": False,
        "ws_stop_event": threading.Event(),
        "req_meta": {},
        "balance": 100.0,
        "strategies": {"KOOLKID": None},
        "loginid": "CR123",
        "active_profile": "KOOLKID",
        "profile_budgets": server._new_profile_budget_map(),
        "contract_meta": {},
        "bot_auto_close_timers": {},
    }


def test_legacy_token_execute_deriv_trade_keeps_old_buy_payload(monkeypatch):
    state = _base_state("legacy")
    monkeypatch.setattr(server, "clients", {"cid-legacy": state})
    called = []
    monkeypatch.setattr(server, "_execute_oauth_options_trade_engine", lambda *a, **k: called.append((a, k)) or (False, "wrong path"))

    ok, msg = server.execute_deriv_trade({
        "client_id": "cid-legacy",
        "state": state,
        "contract_type": "OVER",
        "stake": 1.0,
        "symbol": "R_10",
        "barrier": 5,
        "duration": 1,
        "duration_unit": "t",
    })

    assert ok is True
    assert msg == "Trade sent"
    assert called == []
    assert state["ws"].messages[-1]["buy"] == 1
    assert state["ws"].messages[-1]["parameters"]["symbol"] == "R_10"


def test_oauth_execute_deriv_trade_routes_to_oauth_engine(monkeypatch):
    state = _base_state("oauth")
    monkeypatch.setattr(server, "clients", {"cid-oauth": state})
    captured = {}

    def fake_engine(trade_request, *, state, req_id, stake, duration, duration_unit):
        captured.update({
            "trade_request": trade_request,
            "state": state,
            "req_id": req_id,
            "stake": stake,
            "duration": duration,
            "duration_unit": duration_unit,
        })
        return True, "oauth engine"

    monkeypatch.setattr(server, "_execute_oauth_options_trade_engine", fake_engine)

    ok, msg = server.execute_deriv_trade({
        "client_id": "cid-oauth",
        "state": state,
        "contract_type": "OVER",
        "stake": 1.0,
        "symbol": "R_10",
        "barrier": 5,
        "duration": 1,
        "duration_unit": "t",
    })

    assert ok is True
    assert msg == "oauth engine"
    assert captured["state"] is state
    assert captured["stake"] == 1.0
    assert state["ws"].messages == []


def test_pat_token_routes_to_options_trade_engine(monkeypatch):
    state = _base_state("pat")
    state["api_token"] = "pat_manual_user_token"
    monkeypatch.setattr(server, "clients", {"cid-pat": state})
    captured = {}

    def fake_engine(trade_request, *, state, req_id, stake, duration, duration_unit):
        captured.update({
            "trade_request": trade_request,
            "state": state,
            "req_id": req_id,
            "stake": stake,
            "duration": duration,
            "duration_unit": duration_unit,
        })
        return True, "pat options engine"

    monkeypatch.setattr(server, "_execute_oauth_options_trade_engine", fake_engine)

    ok, msg = server.execute_deriv_trade({
        "client_id": "cid-pat",
        "state": state,
        "contract_type": "OVER",
        "stake": 1.0,
        "symbol": "R_10",
        "barrier": 5,
        "duration": 1,
        "duration_unit": "t",
    })

    assert ok is True
    assert msg == "pat options engine"
    assert captured["state"] is state
    assert captured["stake"] == 1.0
    assert server._deriv_trade_connection_mode(state) == "pat"
    assert server._uses_new_deriv_trade_api(state) is True
    assert state["ws"].messages == []


def test_pat_ws_open_never_sends_authorize_and_waits_for_balance(monkeypatch):
    state = _base_state("pat")
    state.update({
        "ws_nonce": 7,
        "ws_connected": False,
        "ws_transport_connected": False,
        "api_token": "pat_manual_user_token",
        "api_token_type": "pat",
        "options_account_id": "DOT789",
        "pat_options_account_id": "DOT789",
    })
    ws = DummyWs()
    monkeypatch.setattr(server, "clients", {"cid-pat-open": state})
    monkeypatch.setattr(server, "_start_deriv_keepalive", lambda *a, **k: None)
    monkeypatch.setattr(server, "_restore_required_tick_subscriptions", lambda *a, **k: None)
    monkeypatch.setattr(server, "_get_tick_stream_health", lambda *a, **k: {"tick_stream_healthy": True})
    monkeypatch.setattr(server, "_build_balance_payload", lambda state: {"balance": state.get("balance", 0.0)})
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *a, **k: None)
    monkeypatch.setattr(server, "emit_profile_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(server, "request_human_seed", lambda *a, **k: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *a, **k: None)

    server.handle_on_open("cid-pat-open", ws, 7)

    assert state["ws_transport_connected"] is True
    assert state["ws_connected"] is False
    assert {"authorize": "pat_manual_user_token"} not in ws.messages
    assert ws.messages == [{"balance": 1, "subscribe": 1}]

    server.handle_on_message(
        "cid-pat-open",
        ws,
        json.dumps({"balance": {"balance": 123.45}, "msg_type": "balance"}),
        7,
    )

    assert state["ws_connected"] is True
    assert state["loginid"] == "DOT789"
    assert state["balance"] == 123.45
