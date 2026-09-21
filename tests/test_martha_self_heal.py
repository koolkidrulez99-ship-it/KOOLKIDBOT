import json
import threading
import time
from pathlib import Path

import server
from strategies.martha_self_heal import (
    ensure_martha_health,
    martha_health_snapshot,
    record_martha_failure,
    record_martha_success,
)


class ProposalRetrySocket:
    def __init__(self, state):
        self.state = state
        self.sent = []

    def send(self, raw):
        payload = json.loads(raw)
        self.sent.append(payload)
        if len(self.sent) == 2:
            waiter = self.state["_proposal_waiters"][payload["req_id"]]
            waiter["proposal"] = {"id": "fresh-proposal", "ask_price": 1.0}
            waiter["event"].set()


class RecordingSocket:
    def __init__(self):
        self.sent = []

    def send(self, raw):
        self.sent.append(json.loads(raw))


def test_proposal_timeout_retries_once_with_fresh_request_id():
    state = {
        "martha_ai": {"enabled": True},
        "_proposal_waiters": {},
        "proposal_rate_limited_until": 0.0,
    }
    state["ws"] = ProposalRetrySocket(state)

    proposal, error = server._request_digit_proposal_for_buy(
        "martha-test",
        state,
        {"proposal": 1, "req_id": 101, "amount": 1, "contract_type": "DIGITOVER"},
        timeout_sec=0.01,
    )

    assert error is None
    assert proposal["id"] == "fresh-proposal"
    assert len(state["ws"].sent) == 2
    assert state["ws"].sent[0]["req_id"] == 101
    assert state["ws"].sent[1]["req_id"] != 101
    assert state["_proposal_waiters"] == {}
    events = martha_health_snapshot(state)["events"]
    assert any(row["event"] == "proposal_retry" for row in events)


def test_stale_waiter_is_released_without_sending_a_buy(monkeypatch):
    event = threading.Event()
    waiter = {"event": event, "proposal": None, "error": None, "created_at": time.time() - 30}
    ws = RecordingSocket()
    state = {
        "martha_ai": {"enabled": True},
        "_proposal_waiters": {7: waiter, "7": waiter},
        "bot_auto_close_timers": {},
        "contract_meta": {},
        "open_contract_subs": {},
        "ws": ws,
        "ws_connected": True,
    }
    emitted = []
    monkeypatch.setattr(server.socketio, "emit", lambda name, data, room=None: emitted.append((name, data, room)))

    result = server._run_martha_self_heal_check("martha-test", state)

    assert event.is_set()
    assert state["_proposal_waiters"] == {}
    assert ws.sent == []
    assert "expired_proposal_waiter" in result["actions"]
    assert emitted[0][0] == "martha_ai_recovery"


def test_missing_settlement_requests_only_contract_reconciliation():
    ws = RecordingSocket()
    state = {
        "martha_ai": {"enabled": True},
        "_proposal_waiters": {},
        "bot_auto_close_timers": {},
        "open_contract_subs": {},
        "ws": ws,
        "ws_connected": True,
        "contract_meta": {
            "456": {"_latency": {"buy_confirm": server._trade_latency_now() - 20.0}}
        },
    }

    result = server._run_martha_self_heal_check("martha-test", state)

    assert "refreshed_missing_settlement" in result["actions"]
    assert ws.sent == [{"proposal_open_contract": 1, "contract_id": 456, "subscribe": 1}]
    assert all("buy" not in payload for payload in ws.sent)


def test_open_long_duration_contract_is_not_refreshed_before_expiry():
    ws = RecordingSocket()
    state = {
        "martha_ai": {"enabled": True},
        "_proposal_waiters": {},
        "bot_auto_close_timers": {},
        "open_contract_subs": {},
        "ws": ws,
        "ws_connected": True,
        "contract_meta": {
            "789": {
                "duration": 5,
                "duration_unit": "m",
                "_latency": {"buy_confirm": server._trade_latency_now() - 20.0},
            }
        },
    }

    result = server._run_martha_self_heal_check("martha-test", state)

    assert "refreshed_missing_settlement" not in result["actions"]
    assert ws.sent == []


def test_repeated_failures_safe_stop_and_success_resets_counter():
    state = {}
    health = ensure_martha_health(state)
    assert health["max_failures"] == 3

    record_martha_failure(state, "proposal_timeout")
    record_martha_failure(state, "proposal_timeout")
    assert martha_health_snapshot(state)["safe_stopped"] is False
    record_martha_failure(state, "proposal_timeout")
    assert martha_health_snapshot(state)["safe_stopped"] is True

    record_martha_success(state, "proposal_retry_succeeded")
    snapshot = martha_health_snapshot(state)
    assert snapshot["safe_stopped"] is False
    assert snapshot["consecutive_failures"] == 0


def test_server_safe_stop_disables_only_active_strategy_auto(monkeypatch):
    class Strategy:
        auto_trade = True

    active = Strategy()
    other = Strategy()
    state = {
        "active_profile": "KOOLKID",
        "strategies": {"KOOLKID": active, "HUMAN": other},
    }
    emitted = []
    monkeypatch.setattr(server.socketio, "emit", lambda name, data, room=None: emitted.append((name, data)))

    server._martha_failure("test", state, "one")
    server._martha_failure("test", state, "two")
    server._martha_failure("test", state, "three")

    assert active.auto_trade is False
    assert other.auto_trade is True
    assert emitted[-1][1]["action"] == "safe_stop_automation"


def test_koolkid_frontend_exposes_safe_stalled_request_cleanup():
    source = (Path(__file__).resolve().parents[1] / "static" / "js" / "profiles" / "koolkid.js").read_text(encoding="utf-8")
    assert "window.recoverKoolkidMartingaleFromMartha" in source
    assert "st.requestGeneration = Number(st.requestGeneration || 0) + 1;" in source
    assert 'st.status = recovery.safe_stop ? "Stopped: repeated connection failures"' in source
