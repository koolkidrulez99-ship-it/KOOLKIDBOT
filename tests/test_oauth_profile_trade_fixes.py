from types import SimpleNamespace

import server
from deriv_engines.oauth_engine import OAuthDerivTradeEngine
from deriv_engines.trade_intent import TradeIntent
from deriv_engines.unchain_barrier import sanitize_unchain_higher_lower_barrier


class DummyWs:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def send(self, payload):
        if self.fail:
            raise RuntimeError("temporary backpressure")
        self.sent.append(payload)


def test_kidgx_reset_clears_trade_state_flags():
    strat = SimpleNamespace(
        isTrading=True,
        tradeInProgress=True,
        activeContractId="123",
        proposalId="abc",
        waitingForResult=True,
        kidgx_trade_in_progress=True,
        kidgx_waiting_for_result=True,
        kidgx_active_contract_id="123",
        kidgx_proposal_id="abc",
    )
    state = {
        "strategies": {"KOOLKID": strat},
        "active_profile": "KOOLKID",
        "ws_connected": True,
        "api_token_type": "oauth",
        "deriv_account_id": "DOT123",
    }

    server._reset_kidgx_trade_state(
        "cid-kidgx-reset",
        state,
        "KOOLKID",
        meta={"profile": "KOOLKID", "mode": "KIDGX"},
        contract={"profit": 1.23, "status": "won"},
        reason="contract_settled",
    )

    assert strat.isTrading is False
    assert strat.tradeInProgress is False
    assert strat.waitingForResult is False
    assert strat.kidgx_trade_in_progress is False
    assert strat.kidgx_waiting_for_result is False
    assert strat.activeContractId is None
    assert strat.proposalId is None
    assert strat.kidgx_active_contract_id is None
    assert strat.kidgx_proposal_id is None


def test_oauth_kidgx_duplicate_signal_is_blocked_without_touching_legacy(monkeypatch):
    calls = []

    class KidGxStrategy:
        kidgx_auto = True
        kidgx_trade_in_progress = True

        def check_auto_trade_signal(self):
            return {"mode": "KIDGX", "type": "DIFFERS", "barrier": 5}

    state = {
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": KidGxStrategy()},
        "api_token_type": "oauth",
        "api_token": "oauth-token",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": DummyWs(),
        "current_symbol": "R_10",
        "auto_stake": 1.0,
    }
    monkeypatch.setattr(server, "send_buy", lambda *args, **kwargs: calls.append((args, kwargs)) or (True, "sent"))

    server.run_auto_trade("cid-kidgx-dup", state)

    assert calls == []


def test_unchain_oauth_higher_routes_to_execute_deriv_trade(monkeypatch):
    cid = "cid-unchain-oauth-route"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state.update({
        "api_token_type": "oauth",
        "api_token": "oauth-token",
        "deriv_account_id": "DOT123",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": DummyWs(),
        "current_symbol": "R_10",
        "balance": 1000.0,
        "last_live_balance": 1000.0,
        "last_known_trade_balance": 1000.0,
    })
    captured = {}
    monkeypatch.setattr(server, "resolve_new_api_symbol", lambda state, symbol, context="", client_id=None: ("R_10", None))
    monkeypatch.setattr(
        server,
        "_get_contracts_for_symbol",
        lambda client_id, state, symbol: ({"available": [{"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1}]}, None),
    )
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    def fake_execute(trade_request):
        captured.update(trade_request)
        return True, "Trade sent"

    monkeypatch.setattr(server, "execute_deriv_trade", fake_execute)

    ok, msg = server._send_unchain_hl_trade(
        cid,
        side="HIGHER",
        stake=1.0,
        symbol="R_10",
        barrier="+0.12",
        duration=5,
        duration_unit="t",
    )

    assert ok is True
    assert msg == "HIGHER trade sent"
    assert captured["profile"] == "UNCHAIN"
    assert captured["contract_type"] == "CALL"
    assert captured["symbol"] == "R_10"
    assert captured["duration"] == 5
    assert captured["duration_unit"] == "t"
    assert state["ws_connected"] is True


def test_unchain_oauth_digit_barriers_are_sanitized_to_relative_price_barriers(monkeypatch):
    cid = "cid-unchain-oauth-barrier"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state.update({
        "api_token_type": "oauth",
        "api_token": "oauth-token",
        "deriv_account_id": "DOT123",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": DummyWs(),
        "current_symbol": "R_10",
        "balance": 1000.0,
        "last_live_balance": 1000.0,
        "last_known_trade_balance": 1000.0,
    })
    captured = {}
    monkeypatch.setattr(server, "resolve_new_api_symbol", lambda state, symbol, context="", client_id=None: ("R_10", None))
    monkeypatch.setattr(
        server,
        "_get_contracts_for_symbol",
        lambda client_id, state, symbol: ({"available": [
            {"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1},
            {"contract_type": "PUT", "sentiment": "down", "contract_category": "callput", "barriers": 1},
        ]}, None),
    )
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    def fake_execute(trade_request):
        captured.setdefault(trade_request["contract_type"], []).append(trade_request)
        return True, "Trade sent"

    monkeypatch.setattr(server, "execute_deriv_trade", fake_execute)

    ok_higher, _ = server._send_unchain_hl_trade(
        cid,
        side="HIGHER",
        stake=1.0,
        symbol="R_10",
        barrier="6",
        duration=1,
        duration_unit="t",
    )
    ok_lower, _ = server._send_unchain_hl_trade(
        cid,
        side="LOWER",
        stake=1.0,
        symbol="R_10",
        barrier="Under 9",
        duration=1,
        duration_unit="t",
    )

    assert ok_higher is True
    assert ok_lower is True
    assert captured["CALL"][0]["barrier"] == "+0.10"
    assert captured["PUT"][0]["barrier"] == "-0.10"
    assert state["ws_connected"] is True


def test_unchain_oauth_uses_exact_contract_type_from_contracts_for(monkeypatch):
    cid = "cid-unchain-oauth-exact-contract"
    server.clients.pop(cid, None)
    server.init_client(cid)
    state = server.clients[cid]
    state.update({
        "api_token_type": "oauth",
        "api_token": "oauth-token",
        "deriv_account_id": "DOT123",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": DummyWs(),
        "current_symbol": "R_10",
        "balance": 1000.0,
        "last_live_balance": 1000.0,
        "last_known_trade_balance": 1000.0,
    })
    captured = {}
    monkeypatch.setattr(server, "resolve_new_api_symbol", lambda state, symbol, context="", client_id=None: ("R_10", None))
    monkeypatch.setattr(
        server,
        "_get_contracts_for_symbol",
        lambda client_id, state, symbol: ({"available": [
            {"contract_type": "HIGHER", "sentiment": "up", "contract_category": "callput", "barriers": 1, "barrier": "+0.17"},
            {"contract_type": "LOWER", "sentiment": "down", "contract_category": "callput", "barriers": 1, "barrier": "-0.17"},
        ]}, None),
    )
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    def fake_execute(trade_request):
        captured.update(trade_request)
        return True, "Trade sent"

    monkeypatch.setattr(server, "execute_deriv_trade", fake_execute)

    ok, _ = server._send_unchain_hl_trade(
        cid,
        side="HIGHER",
        stake=1.0,
        symbol="R_10",
        barrier="6",
        duration=1,
        duration_unit="t",
    )

    assert ok is True
    assert captured["contract_type"] == "HIGHER"
    assert captured["barrier"] == "+0.17"
    assert captured["req_meta"]["deriv_contract_type"] == "HIGHER"
    assert captured["req_meta"]["underlying_symbol"] == "R_10"


def test_unchain_barrier_sanitizer_preserves_signed_price_barrier_and_fixes_side():
    assert sanitize_unchain_higher_lower_barrier("+0.12", "CALL") == "+0.12"
    assert sanitize_unchain_higher_lower_barrier("-0.12", "CALL") == "+0.12"
    assert sanitize_unchain_higher_lower_barrier("+0.12", "PUT") == "-0.12"
    assert sanitize_unchain_higher_lower_barrier("0.15", "HIGHER") == "+0.15"
    assert sanitize_unchain_higher_lower_barrier("9", "LOWER") == "-0.10"


def test_oauth_engine_unchain_keeps_relative_barrier_in_proposal():
    proposal_payloads = []
    state = {
        "ws": DummyWs(),
        "ws_connected": True,
        "api_token_type": "oauth",
        "deriv_account_id": "DOT123",
        "req_meta": {},
    }
    deps = {
        "logger": server.logger,
        "connection_mode": lambda state: "oauth",
        "is_demo": lambda account: True,
        "mask_account": lambda account_id: account_id,
        "ws_ready_state": lambda state: "OPEN",
        "otp_authenticated": lambda state: True,
        "active_symbols": lambda client_id, state: ([{"symbol": "R_10"}], None),
        "contracts_for": lambda client_id, state, symbol: ({"available": [{"contract_type": "HIGHER", "sentiment": "up", "contract_category": "callput", "barriers": 1}]}, None),
        "legacy_aliases": {},
        "duration_matches": lambda item, duration, duration_unit: True,
        "safe_payload": server._safe_deriv_payload_text,
        "proposal_payload_for_connection": lambda state, payload: payload,
        "request_proposal": lambda client_id, state, payload, timeout_sec=5.0: proposal_payloads.append(payload) or ({"id": "proposal-1", "ask_price": 1.0}, None),
        "new_req_id": lambda: 999,
        "debug_log": lambda *args, **kwargs: None,
        "safe_float": server._safe_float,
        "now_time": server.now_time,
        "stamp_latency": lambda meta, stage: None,
        "mark_ws_unhealthy": lambda *args, **kwargs: None,
        "should_force_reconnect": lambda state, exc: False,
    }
    intent = TradeIntent(
        client_id="cid-unchain-engine",
        req_id=321,
        profile="UNCHAIN",
        strategy_name="UNCHAIN",
        button="UNCHAIN HIGHER",
        contract_type="CALL",
        stake=1.0,
        symbol="R_10",
        barrier="6",
        duration=1,
        duration_unit="t",
    )

    ok, msg = OAuthDerivTradeEngine(deps).execute(intent, state=state)

    assert ok is True
    assert msg == "Trade sent"
    assert proposal_payloads[-1]["contract_type"] == "HIGHER"
    assert proposal_payloads[-1]["barrier"] == "+0.10"
    assert proposal_payloads[-1]["duration"] == 1
    assert proposal_payloads[-1]["duration_unit"] == "t"
    assert proposal_payloads[-1]["underlying_symbol"] == "R_10"
    assert "symbol" not in proposal_payloads[-1]
    assert state["ws_connected"] is True


def test_oauth_engine_nonfatal_buy_send_error_does_not_reconnect():
    marked = []
    state = {
        "ws": DummyWs(fail=True),
        "ws_connected": True,
        "api_token_type": "oauth",
        "deriv_account_id": "DOT123",
        "req_meta": {},
    }
    deps = {
        "logger": server.logger,
        "connection_mode": lambda state: "oauth",
        "is_demo": lambda account: True,
        "mask_account": lambda account_id: account_id,
        "ws_ready_state": lambda state: "OPEN",
        "otp_authenticated": lambda state: True,
        "active_symbols": lambda client_id, state: ([{"symbol": "R_10"}], None),
        "contracts_for": lambda client_id, state, symbol: ({"available": [{"contract_type": "DIGITOVER", "barriers": 1}]}, None),
        "legacy_aliases": {},
        "duration_matches": lambda item, duration, duration_unit: True,
        "safe_payload": server._safe_deriv_payload_text,
        "proposal_payload_for_connection": lambda state, payload: payload,
        "request_proposal": lambda client_id, state, payload, timeout_sec=5.0: ({"id": "proposal-1", "ask_price": 1.0}, None),
        "new_req_id": lambda: 999,
        "debug_log": lambda *args, **kwargs: None,
        "safe_float": server._safe_float,
        "now_time": server.now_time,
        "stamp_latency": lambda meta, stage: None,
        "mark_ws_unhealthy": lambda *args, **kwargs: marked.append((args, kwargs)),
        "should_force_reconnect": lambda state, exc: False,
    }
    intent = TradeIntent(
        client_id="cid-oauth-engine",
        req_id=123,
        profile="KOOLKID",
        strategy_name="KidGx",
        button="KidGx",
        contract_type="OVER",
        stake=1.0,
        symbol="R_10",
        barrier=3,
        duration=1,
        duration_unit="t",
        mode="KIDGX",
    )

    ok, msg = OAuthDerivTradeEngine(deps).execute(intent, state=state)

    assert ok is False
    assert "temporary backpressure" in msg
    assert marked == []
    assert state["ws_connected"] is True
