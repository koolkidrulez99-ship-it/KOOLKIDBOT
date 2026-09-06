import json
from types import SimpleNamespace

import server
from deriv_engines.oauth_engine import OAuthDerivTradeEngine
from deriv_engines.trade_intent import TradeIntent
from deriv_engines.unchain_barrier import (
    sanitize_unchain_higher_lower_barrier,
    validate_unchain_higher_lower_barrier,
)


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
        lambda client_id, state, symbol: ({"available": [{
            "contract_type": "CALL",
            "sentiment": "up",
            "contract_category": "callput",
            "barriers": 1,
            "expiry_type": "tick",
            "min_contract_duration": "1t",
            "max_contract_duration": "10t",
        }]}, None),
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


def test_unchain_oauth_higher_and_lower_use_fresh_call_put_relative_barriers(monkeypatch):
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
            {"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1, "barrier": "+0.10", "expiry_type": "tick", "min_contract_duration": "1t", "max_contract_duration": "10t"},
            {"contract_type": "PUT", "sentiment": "down", "contract_category": "callput", "barriers": 1, "barrier": "-0.10", "expiry_type": "tick", "min_contract_duration": "1t", "max_contract_duration": "10t"},
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
        barrier="+0.10",
        duration=1,
        duration_unit="t",
    )
    ok_lower, _ = server._send_unchain_hl_trade(
        cid,
        side="LOWER",
        stake=1.0,
        symbol="R_10",
        barrier="-0.10",
        duration=1,
        duration_unit="t",
    )

    assert ok_higher is True
    assert ok_lower is True
    assert captured["CALL"][0]["barrier"] == "+0.10"
    assert captured["PUT"][0]["barrier"] == "-0.10"
    assert state["ws_connected"] is True


def test_unchain_oauth_blocks_obsolete_higher_lower_contract_type_from_contracts_for(monkeypatch):
    cid = "cid-unchain-oauth-blocks-obsolete-contract"
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

    ok, msg = server._send_unchain_hl_trade(
        cid,
        side="HIGHER",
        stake=1.0,
        symbol="R_10",
        barrier="+0.17",
        duration=1,
        duration_unit="t",
    )

    assert ok is False
    assert "No Deriv Higher/Lower contract is available" in msg
    assert captured == {}


def test_unchain_barrier_sanitizer_preserves_signed_price_barrier_and_fixes_side():
    assert sanitize_unchain_higher_lower_barrier("+0.12", "CALL") == "+0.12"
    assert sanitize_unchain_higher_lower_barrier("-0.12", "CALL") == "+0.12"
    assert sanitize_unchain_higher_lower_barrier("+0.12", "PUT") == "-0.12"
    assert sanitize_unchain_higher_lower_barrier("0.15", "HIGHER") == "+0.15"
    assert sanitize_unchain_higher_lower_barrier("9", "LOWER") == "-9"


def test_unchain_barrier_validator_does_not_treat_barriers_count_as_allowed_value():
    barrier, err = validate_unchain_higher_lower_barrier(
        "+0.12",
        "HIGHER",
        {"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1},
    )

    assert err is None
    assert barrier == "+0.12"


def test_unchain_barrier_validator_accepts_lower_with_unsigned_range_rules():
    barrier, err = validate_unchain_higher_lower_barrier(
        "-0.10",
        "LOWER",
        {
            "contract_type": "PUT",
            "sentiment": "down",
            "contract_category": "callput",
            "barriers": 1,
            "barrier_range": {"min": "0.05", "max": "0.50", "step": "0.01"},
        },
    )

    assert err is None
    assert barrier == "-0.10"


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
        "contracts_for": lambda client_id, state, symbol: ({"available": [{"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1, "barrier": "+0.10"}]}, None),
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
        barrier="+0.10",
        duration=1,
        duration_unit="t",
    )

    ok, msg = OAuthDerivTradeEngine(deps).execute(intent, state=state)

    assert ok is True
    assert msg == "Trade sent"
    assert proposal_payloads[-1]["contract_type"] == "CALL"
    assert proposal_payloads[-1]["barrier"] == "+0.10"
    assert proposal_payloads[-1]["duration"] == 1
    assert proposal_payloads[-1]["duration_unit"] == "t"
    assert proposal_payloads[-1]["underlying_symbol"] == "R_10"
    assert "symbol" not in proposal_payloads[-1]
    assert state["ws_connected"] is True


def test_oauth_engine_unchain_blocks_unsupported_relative_barrier():
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
        "contracts_for": lambda client_id, state, symbol: ({"available": [{"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1, "barrier": "+0.17"}]}, None),
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
        client_id="cid-unchain-engine-blocked",
        req_id=322,
        profile="UNCHAIN",
        strategy_name="UNCHAIN",
        button="UNCHAIN HIGHER",
        contract_type="CALL",
        stake=1.0,
        symbol="R_10",
        barrier="+0.12",
        duration=1,
        duration_unit="t",
    )

    ok, msg = OAuthDerivTradeEngine(deps).execute(intent, state=state)

    assert ok is False
    assert "not supported" in msg
    assert proposal_payloads == []
    assert state["ws_connected"] is True


def test_oauth_engine_unchain_blocks_stale_digit_barrier_text():
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
        "contracts_for": lambda client_id, state, symbol: ({"available": [{"contract_type": "PUT", "sentiment": "down", "contract_category": "callput", "barriers": 1, "barrier": "-0.10"}]}, None),
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
        client_id="cid-unchain-engine-stale-barrier",
        req_id=323,
        profile="UNCHAIN",
        strategy_name="UNCHAIN",
        button="UNCHAIN LOWER",
        contract_type="PUT",
        stake=1.0,
        symbol="R_10",
        barrier="Under 9",
        duration=1,
        duration_unit="t",
    )

    ok, msg = OAuthDerivTradeEngine(deps).execute(intent, state=state)

    assert ok is False
    assert msg == "Invalid UNCHAIN Higher/Lower barrier"
    assert proposal_payloads == []
    assert state["ws_connected"] is True


def test_oauth_engine_unchain_pair_uses_independent_proposals_and_buys():
    proposal_payloads = []
    state = {
        "ws": DummyWs(),
        "ws_connected": True,
        "api_token_type": "oauth",
        "deriv_account_id": "DOT123",
        "req_meta": {},
    }

    def request_proposal(client_id, state, payload, timeout_sec=5.0):
        proposal_payloads.append(dict(payload))
        return {"id": f"proposal-{payload.get('req_id')}", "ask_price": payload.get("amount", 1.0)}, None

    deps = {
        "logger": server.logger,
        "connection_mode": lambda state: "oauth",
        "is_demo": lambda account: True,
        "mask_account": lambda account_id: account_id,
        "ws_ready_state": lambda state: "OPEN",
        "otp_authenticated": lambda state: True,
        "active_symbols": lambda client_id, state: ([{"symbol": "R_10"}], None),
        "contracts_for": lambda client_id, state, symbol: ({"available": [
            {"contract_type": "CALL", "sentiment": "up", "contract_category": "callput", "barriers": 1, "barrier": "+0.10"},
            {"contract_type": "PUT", "sentiment": "down", "contract_category": "callput", "barriers": 1, "barrier": "-0.10"},
        ]}, None),
        "legacy_aliases": {},
        "duration_matches": lambda item, duration, duration_unit: True,
        "safe_payload": server._safe_deriv_payload_text,
        "proposal_payload_for_connection": lambda state, payload: payload,
        "request_proposal": request_proposal,
        "new_req_id": lambda: 999,
        "debug_log": lambda *args, **kwargs: None,
        "safe_float": server._safe_float,
        "now_time": server.now_time,
        "stamp_latency": lambda meta, stage: None,
        "mark_ws_unhealthy": lambda *args, **kwargs: None,
        "should_force_reconnect": lambda state, exc: False,
    }
    engine = OAuthDerivTradeEngine(deps)

    ok_higher, msg_higher = engine.execute(TradeIntent(
        client_id="cid-unchain-engine-pair",
        req_id=401,
        profile="UNCHAIN",
        strategy_name="UNCHAIN",
        button="UNCHAIN HIGHER",
        contract_type="CALL",
        stake=1.0,
        symbol="R_10",
        barrier="+0.10",
        duration=1,
        duration_unit="t",
    ), state=state)
    ok_lower, msg_lower = engine.execute(TradeIntent(
        client_id="cid-unchain-engine-pair",
        req_id=402,
        profile="UNCHAIN",
        strategy_name="UNCHAIN",
        button="UNCHAIN LOWER",
        contract_type="PUT",
        stake=1.0,
        symbol="R_10",
        barrier="-0.10",
        duration=1,
        duration_unit="t",
    ), state=state)

    assert (ok_higher, msg_higher) == (True, "Trade sent")
    assert (ok_lower, msg_lower) == (True, "Trade sent")
    assert proposal_payloads == [
        {
            "proposal": 1,
            "req_id": 401,
            "amount": 1.0,
            "basis": "stake",
            "contract_type": "CALL",
            "currency": "USD",
            "duration": 1,
            "duration_unit": "t",
            "underlying_symbol": "R_10",
            "barrier": "+0.10",
        },
        {
            "proposal": 1,
            "req_id": 402,
            "amount": 1.0,
            "basis": "stake",
            "contract_type": "PUT",
            "currency": "USD",
            "duration": 1,
            "duration_unit": "t",
            "underlying_symbol": "R_10",
            "barrier": "-0.10",
        },
    ]
    assert [json.loads(item) for item in state["ws"].sent] == [
        {"req_id": 401, "buy": "proposal-401", "price": 1.0},
        {"req_id": 402, "buy": "proposal-402", "price": 1.0},
    ]


def _make_human_step_index_state():
    state = server._build_default_client_state()
    state.update({
        "active_profile": "HUMAN",
        "api_token_type": "pat",
        "api_token": "pat_test",
        "deriv_account_id": "DOTSTEP",
        "options_account_id": "DOTSTEP",
        "pat_options_account_id": "DOTSTEP",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": DummyWs(),
        "human_symbol": "stpRNG",
        "current_symbol": "stpRNG",
        "balance": 100.0,
        "last_live_balance": 100.0,
        "last_known_trade_balance": 100.0,
        "last_live_balance_updated_at": 1.0,
        "balance_updated_at": 1.0,
    })
    return state


def _patch_human_step_index_options(monkeypatch, proposal_payloads):
    monkeypatch.setattr(server, "_ensure_trade_socket_ready", lambda client_id, state, emit_error=True: (True, None))
    monkeypatch.setattr(server, "_get_active_symbols_for_state", lambda client_id, state: ([{"symbol": "stpRNG"}], None))
    monkeypatch.setattr(
        server,
        "_get_contracts_for_symbol",
        lambda client_id, state, symbol: ({
            "available": [
                {"contract_type": "CALL", "barriers": 1, "barrier": "+0.10", "barrier_category": "relative"},
                {"contract_type": "PUT", "barriers": 1, "barrier": "-0.10", "barrier_category": "relative"},
            ]
        }, None),
    )
    monkeypatch.setattr(
        server,
        "_request_digit_proposal_for_buy",
        lambda client_id, state, payload, timeout_sec=5.0: proposal_payloads.append(dict(payload)) or ({
            "id": f"proposal-{payload.get('contract_type')}",
            "ask_price": payload.get("amount", 1.0),
            "display_value": payload.get("amount", 1.0),
        }, None),
    )
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *args, **kwargs: None)


def test_human_rise_now_step_index_call_proposal_has_no_barrier_fields(monkeypatch):
    proposal_payloads = []
    state = _make_human_step_index_state()
    monkeypatch.setattr(server, "clients", {"cid-human-rise": state})
    _patch_human_step_index_options(monkeypatch, proposal_payloads)

    ok, msg = server.place_risefall_order("cid-human-rise", {
        "direction": "RISE",
        "stake": 1.0,
        "duration": 5,
        "duration_unit": "t",
        "symbol": "stpRNG",
        "mode": "human_rf",
    })

    assert ok is True
    assert msg == "Trade sent"
    assert proposal_payloads[-1] == {
        "proposal": 1,
        "req_id": proposal_payloads[-1]["req_id"],
        "amount": 1.0,
        "basis": "stake",
        "contract_type": "CALL",
        "currency": "USD",
        "duration": 5,
        "duration_unit": "t",
        "underlying_symbol": "stpRNG",
    }
    assert not any(key in proposal_payloads[-1] for key in ("barrier", "barrier2", "prediction", "edge_gap", "edgeGap"))
    assert json.loads(state["ws"].sent[-1]) == {"req_id": proposal_payloads[-1]["req_id"], "buy": "proposal-CALL", "price": 1.0}


def test_human_fall_now_step_index_put_proposal_has_no_barrier_fields(monkeypatch):
    proposal_payloads = []
    state = _make_human_step_index_state()
    monkeypatch.setattr(server, "clients", {"cid-human-fall": state})
    _patch_human_step_index_options(monkeypatch, proposal_payloads)

    ok, msg = server.place_risefall_order("cid-human-fall", {
        "direction": "FALL",
        "stake": 1.0,
        "duration": 5,
        "duration_unit": "t",
        "symbol": "stpRNG",
        "mode": "human_rf",
    })

    assert ok is True
    assert msg == "Trade sent"
    assert proposal_payloads[-1]["contract_type"] == "PUT"
    assert proposal_payloads[-1]["underlying_symbol"] == "stpRNG"
    assert not any(key in proposal_payloads[-1] for key in ("barrier", "barrier2", "prediction", "edge_gap", "edgeGap"))
    assert json.loads(state["ws"].sent[-1]) == {"req_id": proposal_payloads[-1]["req_id"], "buy": "proposal-PUT", "price": 1.0}


def test_human_auto_rise_fall_step_index_builds_fresh_barrierless_proposals(monkeypatch):
    proposal_payloads = []
    state = _make_human_step_index_state()
    monkeypatch.setattr(server, "clients", {"cid-human-auto-rf": state})
    _patch_human_step_index_options(monkeypatch, proposal_payloads)

    rise_ok, rise_msg = server.place_risefall_order("cid-human-auto-rf", {
        "direction": "RISE",
        "stake": 0.35,
        "duration": 5,
        "duration_unit": "t",
        "symbol": "stpRNG",
        "mode": "human_auto_rise_fall",
    })
    fall_ok, fall_msg = server.place_risefall_order("cid-human-auto-rf", {
        "direction": "FALL",
        "stake": 0.35,
        "duration": 5,
        "duration_unit": "t",
        "symbol": "stpRNG",
        "mode": "human_auto_rise_fall",
    })

    assert (rise_ok, rise_msg) == (True, "Trade sent")
    assert (fall_ok, fall_msg) == (True, "Trade sent")
    assert [payload["contract_type"] for payload in proposal_payloads[-2:]] == ["CALL", "PUT"]
    assert all("underlying_symbol" in payload and "symbol" not in payload for payload in proposal_payloads[-2:])
    assert all(not any(key in payload for key in ("barrier", "barrier2", "prediction", "edge_gap", "edgeGap")) for payload in proposal_payloads[-2:])
    buy_payloads = [json.loads(item) for item in state["ws"].sent[-2:]]
    assert buy_payloads == [
        {"req_id": proposal_payloads[-2]["req_id"], "buy": "proposal-CALL", "price": 0.35},
        {"req_id": proposal_payloads[-1]["req_id"], "buy": "proposal-PUT", "price": 0.35},
    ]


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
