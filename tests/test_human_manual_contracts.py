import human_profile_contracts as hpc
import server


class _DummyWs:
    def __init__(self):
        self.messages = []

    def send(self, payload):
        self.messages.append(payload)


def test_build_human_manual_contract_info_keeps_asians_pair_distinct(monkeypatch):
    available = [
        {"contract_type": "SHARED", "contract_display": "Shared Asians"},
        {"contract_type": "UPLEG", "contract_display": "Asians Up"},
        {"contract_type": "DOWNLEG", "contract_display": "Asians Down"},
    ]

    def fake_score(item, action_key):
        contract_type = str(item.get("contract_type") or "").upper()
        if action_key == "ASIANS_UP":
            return {"SHARED": 90, "UPLEG": 85, "DOWNLEG": 0}.get(contract_type, 0)
        if action_key == "ASIANS_DOWN":
            return {"SHARED": 90, "UPLEG": 0, "DOWNLEG": 85}.get(contract_type, 0)
        return 0

    monkeypatch.setattr(hpc, "_score_contract", fake_score)

    info = hpc.build_human_manual_contract_info(available)

    assert info["ASIANS_UP"]["available"] is True
    assert info["ASIANS_DOWN"]["available"] is True
    assert info["ASIANS_UP"]["contract_type"] == "UPLEG"
    assert info["ASIANS_DOWN"]["contract_type"] == "DOWNLEG"


def test_retry_human_manual_pair_leg_after_error_resends_failed_leg(monkeypatch):
    ws = _DummyWs()
    state = {
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": ws,
        "req_meta": {},
    }
    meta = {
        "profile": "HUMAN",
        "pair_batch_id": 77,
        "pair_batch_size": 2,
        "pair_retry_count": 0,
        "pair_action": "ASIANS_DOWN",
        "stake": 0.35,
        "symbol": "R_10",
        "duration": 2,
        "duration_unit": "t",
        "contract_type": "ASIAND",
        "selected_tick": None,
    }

    monkeypatch.setattr(server, "_ensure_trade_socket_ready", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr(
        server,
        "_request_human_manual_proposal_quote",
        lambda *_args, **_kwargs: ({"id": "proposal-asiand", "ask_price": 0.35}, None),
    )
    monkeypatch.setattr(server, "_reserve_profile_budget", lambda *_args, **_kwargs: (True, "", {"reservation": 2}))
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_new_req_id", lambda: 8080)

    ok, err = server._retry_human_manual_pair_leg_after_error("cid-human", state, meta, "buy failed")

    assert ok is True
    assert err is None
    assert 8080 in state["req_meta"]
    assert state["req_meta"][8080]["pair_retry_count"] == 1
    assert "proposal-asiand" in ws.messages[0]


def test_human_even_odd_pair_uses_trade_send_helper(monkeypatch):
    calls = []
    emitted = []
    state = server._build_default_client_state()
    state.update({
        "active_profile": "HUMAN",
        "api_token_type": "pat",
        "api_token": "pat-token",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": _DummyWs(),
        "current_symbol": "R_10",
        "human_symbol": "R_10",
        "balance": 1000.0,
        "last_live_balance": 1000.0,
        "last_known_trade_balance": 1000.0,
    })
    req_ids = iter([101, 102])

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-human-even-odd", state))
    monkeypatch.setattr(server, "_ensure_trade_socket_ready", lambda *_args, **_kwargs: (True, None))
    monkeypatch.setattr(server, "_reserve_profile_budget", lambda *_args, **_kwargs: (True, "", {"reservation": len(calls) + 1}))
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_new_req_id", lambda: next(req_ids))
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))

    def fake_send(client_id, live_state, req_id, payload, stake):
        calls.append((client_id, req_id, payload, stake))
        return True, "Trade sent"

    monkeypatch.setattr(server, "_send_trade_payload_with_oauth_proposal", fake_send)

    with server.app.test_request_context("/human_parity_trade", method="POST", json={
        "side": "EVEN_ODD",
        "even_stake": 0.35,
        "odd_stake": 0.70,
        "symbol": "R_10",
        "duration": 5,
        "duration_unit": "t",
        "mode": "human_parity_martingale:test-run",
        "batch_id": "batch-1",
    }):
        response = server.human_parity_trade_route()

    data = response.get_json()
    assert data["status"] == "success"
    assert data["placed"] == ["EVEN", "ODD"]
    assert [call[1] for call in calls] == [101, 102]
    assert [call[3] for call in calls] == [0.35, 0.70]
    assert [call[2]["parameters"]["contract_type"] for call in calls] == ["DIGITEVEN", "DIGITODD"]
    assert state["ws"].messages == []
