from trade_execution_state import (
    STATE_CONFIRMED,
    STATE_FAILED,
    STATE_RECONCILING,
    STATE_SUBMITTING,
    get_execution_by_req_id,
    get_records_needing_reconcile,
    handle_reconcile_response,
    mark_disconnect_reconciling,
    register_buy_submission,
    start_reconcile_batch,
)
from ws_recovery import build_post_authorize_requests


def _meta(**overrides):
    base = {
        "profile": "NTT",
        "type": "TOUCH",
        "barrier": "+0.12",
        "stake": 0.35,
        "symbol": "R_25",
        "time": "12:00:00",
        "duration": 5,
        "duration_unit": "t",
        "mode": "MUTANT_AUTO",
        "deriv_contract_type": "ONETOUCH",
        "request_started_at": 100.0,
    }
    base.update(overrides)
    return base


def test_trade_execution_moves_from_submitting_to_reconcile_and_confirms_from_statement():
    state = {}
    register_buy_submission(state, "101", _meta(), confirm_timeout_sec=4.0, now_ts=100.0)

    candidates = get_records_needing_reconcile(state, now_ts=105.0)
    assert len(candidates) == 1
    assert candidates[0]["pending_state"] == STATE_SUBMITTING

    ids = iter(["201", "202"])
    batch = start_reconcile_batch(state, lambda: next(ids), now_ts=105.0)
    assert batch is not None

    request_ids = [payload["req_id"] for payload in batch["requests"]]
    handle_reconcile_response(state, request_ids[0], {"portfolio": {"contracts": []}}, now_ts=105.1)
    result = handle_reconcile_response(
        state,
        request_ids[1],
        {
            "statement": {
                "transactions": [
                    {
                        "action_type": "buy",
                        "amount": 0.35,
                        "symbol": "R_25",
                        "contract_id": "555",
                        "contract_type": "ONETOUCH",
                        "transaction_time": 101.0,
                    }
                ]
            }
        },
        now_ts=105.2,
    )

    assert result["completed"] is True
    assert result["confirmed"][0]["contract_id"] == "555"
    record = get_execution_by_req_id(state, "101")
    assert record["pending_state"] == STATE_CONFIRMED
    assert record["contract_id"] == "555"


def test_trade_execution_reconcile_fails_when_trade_never_appears():
    state = {}
    register_buy_submission(state, "301", _meta(symbol="R_50"), confirm_timeout_sec=3.0, now_ts=100.0)

    ids = iter(["401", "402"])
    batch = start_reconcile_batch(state, lambda: next(ids), now_ts=104.0)
    assert batch is not None
    request_ids = [payload["req_id"] for payload in batch["requests"]]
    handle_reconcile_response(state, request_ids[0], {"portfolio": {"contracts": []}}, now_ts=104.1)
    result = handle_reconcile_response(state, request_ids[1], {"statement": {"transactions": []}}, now_ts=104.2)

    assert result["completed"] is True
    assert result["failed"][0]["req_id"] == "301"
    record = get_execution_by_req_id(state, "301")
    assert record["pending_state"] == STATE_FAILED


def test_disconnect_marks_submitting_requests_reconciling():
    state = {}
    register_buy_submission(state, "901", _meta(symbol="R_75"), confirm_timeout_sec=4.0, now_ts=100.0)
    changed = mark_disconnect_reconciling(state, now_ts=101.0, reason="websocket_disconnected")
    assert len(changed) == 1
    assert changed[0]["pending_state"] == STATE_RECONCILING


def test_post_authorize_requests_restore_ticks_balance_and_confirmed_contracts():
    state = {
        "current_symbol": "R_10",
        "human_symbol": "R_25",
        "unchain_scanner": {"running": True, "symbols": ["R_50", "R_25"]},
        "koolkid_golden_card": {"running": True, "symbols": ["JD10", "R_10"]},
        "unchain_hl": {"active_contracts": {}},
        "ntt": {"active_contracts": {}},
    }
    register_buy_submission(state, "701", _meta(symbol="R_10"), confirm_timeout_sec=4.0, now_ts=100.0)
    record = get_execution_by_req_id(state, "701")
    record["pending_state"] = STATE_CONFIRMED
    record["contract_id"] = "888"
    state["trade_execution"]["contract_index"]["888"] = record["execution_id"]

    requests = build_post_authorize_requests(state, include_balance=True)
    assert {"ticks": "R_10", "subscribe": 1} in requests
    assert {"ticks": "R_25", "subscribe": 1} in requests
    assert {"ticks": "R_50", "subscribe": 1} in requests
    assert {"ticks": "JD10", "subscribe": 1} in requests
    assert {"balance": 1, "subscribe": 1} in requests
    assert {"proposal_open_contract": 1, "contract_id": 888, "subscribe": 1} in requests
