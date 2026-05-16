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
    monkeypatch.setattr(server, "_execute_oauth_pat_trade_engine", lambda *a, **k: called.append((a, k)) or (False, "wrong path"))

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

    monkeypatch.setattr(server, "_execute_oauth_pat_trade_engine", fake_engine)

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
