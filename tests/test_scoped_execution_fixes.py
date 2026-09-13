import json
import queue
import threading
from types import SimpleNamespace

import pytest

import server


@pytest.fixture
def settlement(monkeypatch):
    emitted = []
    strategy = server.HumanStrategy()
    state = {
        "active_profile": "HUMAN",
        "strategies": {"HUMAN": strategy},
        "current_symbol": "R_10",
        "contract_meta": {},
        "human_pending_contracts": {},
        "processed_contract_ids": set(),
        "balance": 100.0,
        "last_known_trade_balance": 100.0,
        "profile_budgets": server._new_profile_budget_map(),
    }
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server.socketio, "emit", lambda event, data=None, **kwargs: emitted.append((event, dict(data or {}))))
    monkeypatch.setattr(server, "send_stats_update", lambda *args: None)
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *args: None)
    return state, strategy, emitted


def test_human_expired_pairs_keep_current_metadata_and_count_each_result_once(settlement):
    state, strategy, emitted = settlement
    expected_profit = 0
    for number in range(6):
        direction = "RISE" if number % 2 == 0 else "FALL"
        contract_type = "CALL" if direction == "RISE" else "PUT"
        profit = 0.31 if direction == "RISE" else -0.35
        expected_profit += profit
        meta = {
            "profile": "HUMAN", "type": direction, "contract_type": contract_type,
            "stake": 0.35, "symbol": "stpRNG", "duration": 1, "duration_unit": "t",
            "mode": "HUMAN_RF_MARTINGALE", "batch_id": f"pair-{number // 2}",
            "leg_action": direction, "dual_market_batch_id": f"dual-{number // 2}",
            "dual_market_leg_index": number % 2,
        }
        state["contract_meta"][str(number + 1)] = meta
        contract = {
            "contract_id": number + 1, "contract_type": contract_type,
            "status": "open", "is_expired": 1, "is_sold": 0,
            "profit": profit, "buy_price": 0.35,
        }
        server.process_contract("test", contract)
        server.process_contract("test", contract)
        result = [data for event, data in emitted if event == "trade_result"][-1]
        for field in ("type", "contract_type", "batch_id", "leg_action", "symbol", "dual_market_batch_id", "dual_market_leg_index"):
            assert result[field] == meta[field]
        assert result["contract_id"] == number + 1
        assert result["profit"] == pytest.approx(profit)
        assert contract.get("is_settled") is None
    assert len([event for event, _ in emitted if event == "trade_result"]) == 6
    assert len(strategy.trade_history) == 6
    assert strategy.total_wins == strategy.total_losses == 3
    assert strategy.session_profit == pytest.approx(expected_profit)
    assert len({entry["contract_id"] for entry in strategy.trade_history}) == 6


def test_stale_strategy_entry_is_not_mutated_or_reused(settlement):
    state, _, emitted = settlement
    stale = {"contract_id": "old", "batch_id": "old-pair", "type": "FALL", "profit": 10, "result": "WIN"}
    state["strategies"]["HUMAN"] = SimpleNamespace(
        on_contract=lambda *args: None, get_last_trade_entry=lambda: stale,
    )
    state["contract_meta"]["new"] = {"profile": "HUMAN", "type": "RISE", "batch_id": "new-pair", "stake": 0.35}
    server.process_contract("test", {"contract_id": "new", "is_expired": 1, "status": "open", "profit": -0.35})
    result = next(data for event, data in emitted if event == "trade_result")
    assert result["batch_id"] == "new-pair"
    assert result["type"] == "RISE"
    assert result["result"] == "LOSS"
    assert stale == {"contract_id": "old", "batch_id": "old-pair", "type": "FALL", "profit": 10, "result": "WIN"}


@pytest.mark.parametrize("profile", ["KOOLKID", "JOKERJOE"])
def test_auto_reader_can_deliver_proposals_and_next_trade_runs(monkeypatch, profile):
    outgoing = queue.Queue()
    outcomes = queue.Queue()
    state = {
        "active_profile": profile, "current_symbol": "R_10", "ws_nonce": 1,
        "ws_connected": True, "api_token_type": "pat",
        "ws": SimpleNamespace(send=lambda payload: outgoing.put(json.loads(payload))),
        "auto_stake": 0.35,
        "strategies": {profile: SimpleNamespace(check_auto_trade_signal=lambda: {
            "type": "OVER", "barrier": 5, "mode": "KOOLLUCK" if profile == "KOOLKID" else "sludgeX",
        })},
    }
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server, "_guard_client_license_for_runtime", lambda *args: True)
    monkeypatch.setattr(server, "_proposal_rate_limit_wait_message", lambda *args: None)

    def buy(client_id, contract_type, stake, symbol, barrier, **kwargs):
        assert (contract_type, stake, symbol, barrier) == ("OVER", 0.35, "R_10", 5)
        outcomes.put(server._request_digit_proposal_for_buy(client_id, state, {
            "proposal": 1, "req_id": 7, "contract_type": "DIGITOVER", "amount": 0.35,
            "basis": "stake", "currency": "USD", "underlying_symbol": "R_10",
            "duration": 1, "duration_unit": "t", "barrier": "5",
        }, timeout_sec=1))
        return True, "Sent"

    monkeypatch.setattr(server, "send_buy", buy)
    for proposal_id in ("first", "next"):
        assert server._schedule_profile_auto_trade("test", state)
        request = outgoing.get(timeout=1)
        assert not server._schedule_profile_auto_trade("test", state)
        server.handle_on_message("test", state["ws"], json.dumps({
            "msg_type": "proposal", "req_id": request["req_id"],
            "proposal": {"id": proposal_id, "ask_price": 0.35},
        }), 1)
        proposal, error = outcomes.get(timeout=1)
        assert error is None
        assert proposal["id"] == proposal_id
        lock = state["_profile_auto_dispatch_lock"]
        assert lock.acquire(timeout=1)
        lock.release()
        assert state["_proposal_waiters"] == {}


@pytest.mark.parametrize("changed", ["active_profile", "ws_nonce", "current_symbol"])
def test_queued_auto_does_not_run_after_context_change(monkeypatch, changed):
    workers = []
    executed = []
    state = {"active_profile": "KOOLKID", "ws_nonce": 1, "current_symbol": "R_10", "ws_connected": True}
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server.threading, "Thread", lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)))
    monkeypatch.setattr(server, "run_auto_trade", lambda *args: executed.append(args))
    assert server._schedule_profile_auto_trade("test", state)
    state[changed] = "changed"
    workers.pop()()
    assert executed == []
    assert not state["_profile_auto_dispatch_lock"].locked()


def test_failure_schedules_exactly_one_reconnect_and_keeps_state(monkeypatch):
    workers = []
    starts = []
    state = {
        "api_token": "test-placeholder", "api_token_type": "pat", "ws_nonce": 1,
        "ws_connected": True, "ws_reconnect_pending": False,
        "contract_meta": {"active": {"profile": "KOOLKID"}}, "profile_budgets": {"unchanged": True},
    }
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_build_balance_payload", lambda state: {})
    monkeypatch.setattr(server, "_log_runtime_subscription_counts", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_start_ws_worker_thread", lambda cid, live_state, **kwargs: starts.append(live_state))
    monkeypatch.setattr(server.threading, "Thread", lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)))
    monkeypatch.setattr(server.time, "sleep", lambda *args: None)
    state["ws"] = SimpleNamespace(close=lambda: server._schedule_ws_reconnect("test", 1))
    server._mark_ws_unhealthy_and_reconnect("test", state, "Test transport failure", emit_error=False)
    assert state["ws_reconnect_pending"] is True
    assert len(workers) == 1
    workers.pop()()
    assert starts == [state]
    assert state["ws_reconnect_pending"] is False
    assert state["contract_meta"] == {"active": {"profile": "KOOLKID"}}
    assert state["profile_budgets"] == {"unchanged": True}


@pytest.mark.parametrize("requested", [None, "stpRNG"])
def test_human_pat_availability_uses_connected_market_metadata(monkeypatch, requested):
    state = {"api_token_type": "pat", "human_symbol": "R_10"}
    calls = []
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server, "_resolve_deriv_underlying_symbol", lambda cid, current, symbol: (symbol, None))

    def contracts(cid, current, symbol, force_refresh=False):
        calls.append((cid, current is state, symbol, force_refresh))
        return {"available": [{"contract_type": "ASIANU", "min_contract_duration": "2t", "max_contract_duration": "10t"}]}, None

    monkeypatch.setattr(server, "_get_contracts_for_symbol", contracts)
    monkeypatch.setattr(server, "_module_fetch_human_manual_contracts_for_state", lambda *args, **kwargs: pytest.fail("Legacy socket must not be used for PAT availability"))
    info, error, symbol = server._fetch_human_manual_contracts_for_state(state, force_refresh=True, symbol=requested)
    assert error is None
    assert symbol == (requested or "R_10")
    assert calls == [("test", True, symbol, True)]
    assert info["ASIANS_UP"]["available"] is True
    assert info["ASIANS_UP"]["contract_type"] == "ASIANU"
    assert info["ASIANS_DOWN"]["available"] is False


def test_human_explicit_legacy_market_returns_consistent_lookup_shape(monkeypatch):
    state = {"api_token_type": "legacy"}
    info = {"HIGH_TICK": {"available": False}}
    monkeypatch.setattr(server, "_fetch_human_manual_contracts_for_symbol", lambda symbol, **kwargs: (info, None))
    assert server._fetch_human_manual_contracts_for_state(state, symbol="R_10") == (info, None, "R_10")


def test_human_pat_availability_failure_is_not_cached_as_unsupported(monkeypatch):
    state = {"api_token_type": "pat", "human_symbol": "R_10"}
    monkeypatch.setattr(server, "clients", {"test": state})
    monkeypatch.setattr(server, "_resolve_deriv_underlying_symbol", lambda *args: ("R_10", None))
    monkeypatch.setattr(server, "_get_contracts_for_symbol", lambda *args, **kwargs: (None, "Connection unavailable"))
    assert server._fetch_human_manual_contracts_for_state(state) == (None, "Connection unavailable", "R_10")


@pytest.mark.parametrize("subscribed", [False, True])
def test_subscription_poll_does_not_restart_warmup_or_duplicate_subscribe(monkeypatch, subscribed):
    sent = []
    state = {
        "ws_connected": True, "ws": SimpleNamespace(send=sent.append),
        "tick_subs": {"R_10": "sub"} if subscribed else {},
        "tick_subscribe_sent_at": {"R_10": 100.0},
        "tick_stream_warmup_until": {"R_10": 110.0},
    }
    monkeypatch.setattr(server.time, "time", lambda: 100.1)
    monkeypatch.setattr(server, "_uses_new_deriv_trade_api", lambda *args: False)
    monkeypatch.setattr(server, "_start_tick_stream_warmup", lambda *args, **kwargs: pytest.fail("Polling is not a new subscription"))
    assert server._ensure_tick_subscription(state, "R_10", client_id="test")
    assert sent == []
    assert state["tick_stream_warmup_until"] == {"R_10": 110.0}


@pytest.mark.parametrize("switch_session", [False, True])
def test_quote_refresh_does_not_block_reader_or_trade_after_session_change(monkeypatch, switch_session):
    quote_started = threading.Event()
    quote_done = threading.Event()
    executed = []
    state = {"active_profile": "KOOLKID", "ws_nonce": 1, "current_symbol": "R_10", "ws_connected": True}
    monkeypatch.setattr(server, "clients", {"test": state})

    def refresh(*args):
        quote_started.set()
        assert quote_done.wait(1)
        if switch_session:
            state["ws_nonce"] = 2
        else:
            raise RuntimeError("Preview unavailable")

    monkeypatch.setattr(server, "_maybe_refresh_koolkid_testtrial_quotes", refresh)
    monkeypatch.setattr(server, "run_auto_trade", lambda *args: executed.append(args))
    assert server._schedule_profile_auto_trade("test", state, refresh_quotes=True)
    assert quote_started.wait(1)
    quote_done.set()
    lock = state["_profile_auto_dispatch_lock"]
    assert lock.acquire(timeout=1)
    lock.release()
    assert len(executed) == (0 if switch_session else 1)
