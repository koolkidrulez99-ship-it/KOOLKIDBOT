import json

import server


class _FakeSocket:
    def __init__(self):
        self.messages = []

    def send(self, value):
        self.messages.append(json.loads(value))


def _state():
    state = server._build_default_client_state()
    state["ws_connected"] = True
    state["ws"] = _FakeSocket()
    state["human_symbol"] = "R_10"
    return state


def test_human_koolkid_profit_sends_immediate_five_percent_accumulator():
    state = _state()
    runtime = server._ensure_human_koolkid_profit_state(state)
    runtime.update({"enabled": True, "running": True, "base_stake": 2, "current_stake": 2})

    ok, _message = server._send_human_koolkid_profit_buy("test-client", state)

    assert ok is True
    payload = state["ws"].messages[-1]
    assert payload["buy"] == 1
    assert payload["price"] == 2
    assert payload["parameters"]["contract_type"] == "ACCU"
    assert payload["parameters"]["growth_rate"] == 0.05
    assert runtime["pending_buy"] is True


def test_human_koolkid_profit_win_reinvests_full_profit_and_loss_resets():
    state = _state()
    runtime = server._ensure_human_koolkid_profit_state(state)
    runtime.update({"enabled": True, "base_stake": 10, "current_stake": 10, "open_contract_id": "1"})

    win = server._settle_human_koolkid_profit(state, {"contract_id": "1", "status": "sold"}, {"stake": 10}, 3.25)
    assert win["result"] == "WIN"
    assert runtime["current_stake"] == 13.25
    assert runtime["status"] == "Starting next accumulator"

    runtime["open_contract_id"] = "2"
    loss = server._settle_human_koolkid_profit(state, {"contract_id": "2", "status": "sold"}, {"stake": 13.25}, -2)
    assert loss["result"] == "LOSS"
    assert runtime["current_stake"] == 10


def test_human_koolkid_profit_closes_once_after_two_ticks(monkeypatch):
    state = _state()
    runtime = server._ensure_human_koolkid_profit_state(state)
    runtime.update({
        "enabled": True,
        "running": True,
        "open_contract_id": "123",
        "entry_tick_seq": 10,
        "close_requested": False,
    })
    calls = []
    monkeypatch.setattr(server, "_request_sell_contract", lambda client_id, contract_id: (calls.append((client_id, contract_id)) or True, "sent"))

    state["_human_tick_seq"] = 11
    server._maybe_human_koolkid_profit_on_tick("test-client", state)
    assert calls == []

    state["_human_tick_seq"] = 12
    server._maybe_human_koolkid_profit_on_tick("test-client", state)
    server._maybe_human_koolkid_profit_on_tick("test-client", state)
    assert calls == [("test-client", "123")]


def test_human_koolkid_profit_off_prevents_next_trade(monkeypatch):
    state = _state()
    runtime = server._ensure_human_koolkid_profit_state(state)
    runtime.update({"enabled": False, "running": False, "open_contract_id": "", "pending_buy": False})
    calls = []
    monkeypatch.setattr(server, "_send_human_koolkid_profit_buy", lambda client_id, current_state: calls.append(client_id))

    server._maybe_human_koolkid_profit_on_tick("test-client", state)

    assert calls == []
