import json

import server
from strategies.jokerjoe import JokerJoeStrategy
from strategies.koolkid import KoolKidStrategy


class DummyWS:
    def __init__(self):
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)


def _tick(symbol, digit, epoch):
    return {
        "symbol": symbol,
        "quote": float(f"100.{int(digit):02d}"),
        "pip_size": 2,
        "epoch": epoch,
    }


def test_jokerjoe_kidgx_differs_has_no_server_side_five_second_throttle(monkeypatch):
    cid = "test-jokerjoe-kidgx-fast"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state.update({
        "active_profile": "JOKERJOE",
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "ws_connected": True,
        "ws": DummyWS(),
        "balance": 1000.0,
        "last_live_balance": 1000.0,
        "last_known_trade_balance": 1000.0,
        "auto_stake": 1.0,
    })
    state["strategies"]["JOKERJOE"] = JokerJoeStrategy()
    strat = state["strategies"]["JOKERJOE"]
    strat.kidgx_auto = True
    strat.set_kidgx_barrier(4)

    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    try:
        server.process_tick(cid, _tick("R_10", 1, 1))
        server.process_tick(cid, _tick("R_10", 2, 2))

        assert len(state["ws"].sent) == 2
        payloads = [json.loads(item) for item in state["ws"].sent]
        assert all(payload.get("parameters", {}).get("contract_type") == "DIGITDIFF" for payload in payloads)
        assert all(str(payload.get("parameters", {}).get("barrier")) == "4" for payload in payloads)
        assert "_temp_jokerjoe_kidgx_next_differs_at" not in state
    finally:
        server.clients.pop(cid, None)


def test_monthly_jokerjoe_kidgx_immediate_trade_uses_selected_digit(monkeypatch):
    cid = "test-monthly-jokerjoe-kidgx-now"
    state = {
        "current_symbol": "R_25",
        "human_symbol": "R_25",
        "auto_stake": 2.5,
    }
    strat = JokerJoeStrategy()
    strat.kidgx_auto = True
    strat.set_kidgx_barrier(7)
    captured = {}

    def fake_send_buy_with_profile(client_id, profile, contract_type, stake, symbol, barrier, **kwargs):
        captured.update({
            "client_id": client_id,
            "profile": profile,
            "contract_type": contract_type,
            "stake": stake,
            "symbol": symbol,
            "barrier": barrier,
            "duration": kwargs.get("duration"),
            "duration_unit": kwargs.get("duration_unit"),
            "mode": kwargs.get("mode"),
        })
        return True, "Trade sent"

    monkeypatch.setattr(server, "_monthly_kidgx_replacement_active", lambda: True)
    monkeypatch.setattr(server, "send_buy_with_profile", fake_send_buy_with_profile)

    ok, msg = server._send_monthly_jokerjoe_kidgx_trade_now(cid, state, strat, reason="barrier_changed")

    assert ok is True
    assert msg == "Trade sent"
    assert captured == {
        "client_id": cid,
        "profile": "JOKERJOE",
        "contract_type": "DIFFERS",
        "stake": 2.5,
        "symbol": "R_25",
        "barrier": 7,
        "duration": 1,
        "duration_unit": "t",
        "mode": "KIDGX",
    }


def test_monthly_koolkid_kidgx_toggle_starts_barrier_analysis(monkeypatch):
    cid = "test-monthly-koolkid-kidgx"
    state = {
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": KoolKidStrategy()},
        "ws_connected": True,
        "ws": DummyWS(),
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: (cid, state))
    monkeypatch.setattr(server, "_monthly_kidgx_replacement_active", lambda: True)
    monkeypatch.setattr(server, "_guard_auto_enable", lambda *args, **kwargs: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    with server.app.test_request_context("/toggle_kidgx_auto", method="POST", json={"profile": "KOOLKID"}):
        response = server.toggle_kidgx_auto_route()
        data = response.get_json()

    strat = state["strategies"]["KOOLKID"]
    assert data["status"] == "success"
    assert data["kidgx_auto"] is True
    assert data["kidgx_replacement"] is True
    assert data["barrier_analysis"] is True
    assert strat.barrier_analysis_running is True
