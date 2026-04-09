import json
import logging
import time
import uuid


LOGGER = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_SUBMITTING = "submitting"
STATE_CONFIRMED = "confirmed"
STATE_FAILED = "failed"
STATE_RECONCILING = "reconciling"

ACTIVE_STATES = {STATE_SUBMITTING, STATE_CONFIRMED, STATE_RECONCILING}
TERMINAL_STATES = {STATE_IDLE, STATE_FAILED}


def _safe_json_copy(value):
    try:
        return json.loads(json.dumps(value))
    except Exception:
        if isinstance(value, dict):
            return {str(k): _safe_json_copy(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_safe_json_copy(item) for item in value]
        return value


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _normalize_req_id(req_id):
    if req_id in (None, ""):
        return None
    text = str(req_id).strip()
    return text or None


def normalize_contract_id(contract_id):
    if contract_id in (None, ""):
        return None
    text = str(contract_id).strip()
    if not text:
        return None
    try:
        return str(int(float(text)))
    except Exception:
        return text


def _default_store():
    return {
        "records": {},
        "req_index": {},
        "contract_index": {},
        "reconcile_waiters": {},
        "last_reconcile_started_at": 0.0,
        "last_reconcile_completed_at": 0.0,
        "reconcile_cooldown_until": 0.0,
    }


def ensure_trade_execution_store(state):
    if not isinstance(state, dict):
        return _default_store()
    store = state.get("trade_execution")
    if not isinstance(store, dict):
        store = _default_store()
        state["trade_execution"] = store
    for key, value in _default_store().items():
        store.setdefault(key, _safe_json_copy(value))
    return store


def _record_key(req_id):
    safe_req_id = _normalize_req_id(req_id)
    if not safe_req_id:
        safe_req_id = f"generated:{uuid.uuid4().hex}"
    return f"req:{safe_req_id}"


def _store_record(store, record):
    execution_id = str(record.get("execution_id") or "").strip()
    if not execution_id:
        execution_id = _record_key(record.get("req_id"))
        record["execution_id"] = execution_id
    store["records"][execution_id] = record
    req_id = _normalize_req_id(record.get("req_id"))
    if req_id:
        store["req_index"][req_id] = execution_id
    contract_id = normalize_contract_id(record.get("contract_id"))
    if contract_id:
        store["contract_index"][contract_id] = execution_id
        record["contract_id"] = contract_id
    return record


def _get_record_by_execution_id(store, execution_id):
    if not execution_id:
        return None
    return store.get("records", {}).get(str(execution_id))


def get_execution_by_req_id(state, req_id):
    store = ensure_trade_execution_store(state)
    safe_req_id = _normalize_req_id(req_id)
    if not safe_req_id:
        return None
    execution_id = store.get("req_index", {}).get(safe_req_id)
    return _get_record_by_execution_id(store, execution_id)


def get_execution_by_contract_id(state, contract_id):
    store = ensure_trade_execution_store(state)
    safe_contract_id = normalize_contract_id(contract_id)
    if not safe_contract_id:
        return None
    execution_id = store.get("contract_index", {}).get(safe_contract_id)
    return _get_record_by_execution_id(store, execution_id)


def _build_record_from_meta(req_id, meta, *, confirm_timeout_sec=4.0, now_ts=None):
    now_value = float(now_ts if now_ts is not None else time.time())
    safe_meta = _safe_json_copy(meta if isinstance(meta, dict) else {})
    request_started_at = _safe_float(safe_meta.get("request_started_at"), now_value)
    if request_started_at <= 0.0:
        request_started_at = now_value
    return {
        "execution_id": _record_key(req_id),
        "req_id": _normalize_req_id(req_id),
        "contract_id": None,
        "pending_state": STATE_SUBMITTING,
        "profile": str(safe_meta.get("profile") or "").upper(),
        "type": safe_meta.get("type"),
        "symbol": str(safe_meta.get("symbol") or "").upper(),
        "stake": round(_safe_float(safe_meta.get("stake"), 0.0), 2),
        "barrier": safe_meta.get("barrier"),
        "duration": safe_meta.get("duration"),
        "duration_unit": safe_meta.get("duration_unit"),
        "mode": safe_meta.get("mode"),
        "deriv_contract_type": safe_meta.get("deriv_contract_type"),
        "meta_snapshot": safe_meta,
        "submitted_at": request_started_at,
        "request_started_at": request_started_at,
        "confirmation_deadline_at": request_started_at + max(3.0, float(confirm_timeout_sec or 0.0)),
        "confirmed_at": 0.0,
        "settled_at": 0.0,
        "updated_at": now_value,
        "failure_reason": "",
        "last_result": None,
        "reconcile_attempts": 0,
        "last_reconcile_at": 0.0,
        "last_reconcile_result": "",
        "reconcile_source": "",
        "trade_placed_emitted": False,
        "trade_result_emitted": False,
    }


def register_buy_submission(state, req_id, meta, *, confirm_timeout_sec=4.0, now_ts=None):
    store = ensure_trade_execution_store(state)
    record = _build_record_from_meta(
        req_id,
        meta,
        confirm_timeout_sec=confirm_timeout_sec,
        now_ts=now_ts,
    )
    return _store_record(store, record)


def update_execution_meta_snapshot(state, req_id, meta, *, now_ts=None):
    record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict):
        return None
    safe_meta = _safe_json_copy(meta if isinstance(meta, dict) else {})
    record["meta_snapshot"] = safe_meta
    record["updated_at"] = float(now_ts if now_ts is not None else time.time())
    if safe_meta.get("profile"):
        record["profile"] = str(safe_meta.get("profile") or "").upper()
    if safe_meta.get("symbol"):
        record["symbol"] = str(safe_meta.get("symbol") or "").upper()
    if safe_meta.get("type"):
        record["type"] = safe_meta.get("type")
    if safe_meta.get("deriv_contract_type"):
        record["deriv_contract_type"] = safe_meta.get("deriv_contract_type")
    return record


def mark_buy_confirmed(state, req_id, contract_id, *, now_ts=None, source="buy_confirmed"):
    store = ensure_trade_execution_store(state)
    record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict):
        return None
    now_value = float(now_ts if now_ts is not None else time.time())
    safe_contract_id = normalize_contract_id(contract_id)
    record["contract_id"] = safe_contract_id
    record["pending_state"] = STATE_CONFIRMED
    record["confirmed_at"] = now_value
    record["updated_at"] = now_value
    record["failure_reason"] = ""
    record["reconcile_source"] = str(source or "")
    record["last_reconcile_result"] = ""
    return _store_record(store, record)


def mark_execution_failed(state, *, req_id=None, contract_id=None, reason="", now_ts=None, source="failed"):
    record = None
    if req_id not in (None, ""):
        record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict) and contract_id not in (None, ""):
        record = get_execution_by_contract_id(state, contract_id)
    if not isinstance(record, dict):
        return None
    record["pending_state"] = STATE_FAILED
    record["updated_at"] = float(now_ts if now_ts is not None else time.time())
    record["failure_reason"] = str(reason or "")
    record["last_reconcile_result"] = str(source or "failed")
    return record


def mark_execution_reconciling(state, *, req_id=None, contract_id=None, reason="", now_ts=None):
    record = None
    if req_id not in (None, ""):
        record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict) and contract_id not in (None, ""):
        record = get_execution_by_contract_id(state, contract_id)
    if not isinstance(record, dict):
        return None
    record["pending_state"] = STATE_RECONCILING
    record["updated_at"] = float(now_ts if now_ts is not None else time.time())
    record["failure_reason"] = str(reason or "")
    return record


def mark_disconnect_reconciling(state, *, now_ts=None, reason="websocket_disconnected"):
    store = ensure_trade_execution_store(state)
    now_value = float(now_ts if now_ts is not None else time.time())
    changed = []
    for record in list(store.get("records", {}).values()):
        if not isinstance(record, dict):
            continue
        if record.get("pending_state") != STATE_SUBMITTING:
            continue
        record["pending_state"] = STATE_RECONCILING
        record["updated_at"] = now_value
        record["failure_reason"] = str(reason or "")
        changed.append(record)
    return changed


def mark_contract_settled(state, contract_id, *, result=None, now_ts=None):
    record = get_execution_by_contract_id(state, contract_id)
    if not isinstance(record, dict):
        return None
    record["pending_state"] = STATE_IDLE
    record["updated_at"] = float(now_ts if now_ts is not None else time.time())
    record["settled_at"] = record["updated_at"]
    record["last_result"] = result
    return record


def prune_trade_execution_store(state, *, now_ts=None, terminal_ttl_sec=600.0):
    store = ensure_trade_execution_store(state)
    now_value = float(now_ts if now_ts is not None else time.time())
    removed = []
    for execution_id, record in list(store.get("records", {}).items()):
        if not isinstance(record, dict):
            store["records"].pop(execution_id, None)
            continue
        pending_state = str(record.get("pending_state") or "").strip().lower()
        if pending_state not in TERMINAL_STATES:
            continue
        updated_at = _safe_float(record.get("updated_at"), 0.0)
        if updated_at > 0.0 and (now_value - updated_at) < float(terminal_ttl_sec or 0.0):
            continue
        removed.append(record)
        store["records"].pop(execution_id, None)
        req_id = _normalize_req_id(record.get("req_id"))
        if req_id:
            store.get("req_index", {}).pop(req_id, None)
        contract_id = normalize_contract_id(record.get("contract_id"))
        if contract_id:
            store.get("contract_index", {}).pop(contract_id, None)
    return removed


def get_records_needing_reconcile(state, *, now_ts=None):
    store = ensure_trade_execution_store(state)
    now_value = float(now_ts if now_ts is not None else time.time())
    candidates = []
    for record in list(store.get("records", {}).values()):
        if not isinstance(record, dict):
            continue
        pending_state = str(record.get("pending_state") or "").strip().lower()
        if pending_state == STATE_RECONCILING:
            candidates.append(record)
            continue
        if pending_state != STATE_SUBMITTING:
            continue
        deadline_at = _safe_float(record.get("confirmation_deadline_at"), 0.0)
        if deadline_at > 0.0 and now_value >= deadline_at:
            candidates.append(record)
    return candidates


def _contract_type_matches(record, candidate):
    meta_snapshot = record.get("meta_snapshot") if isinstance(record.get("meta_snapshot"), dict) else {}
    expected = str(
        meta_snapshot.get("deriv_contract_type")
        or record.get("deriv_contract_type")
        or meta_snapshot.get("type")
        or record.get("type")
        or ""
    ).strip().upper()
    if not expected:
        return True
    candidate_values = [
        candidate.get("contract_type"),
        candidate.get("display_name"),
        candidate.get("shortcode"),
        candidate.get("description"),
        candidate.get("longcode"),
        candidate.get("transaction_type"),
        candidate.get("action_type"),
        candidate.get("action"),
    ]
    candidate_blob = " ".join(str(value or "").upper() for value in candidate_values)
    if not candidate_blob:
        return True
    synonyms = {
        "DIGITOVER": ("DIGITOVER", "OVER"),
        "DIGITUNDER": ("DIGITUNDER", "UNDER"),
        "DIGITMATCH": ("DIGITMATCH", "MATCH"),
        "DIGITDIFF": ("DIGITDIFF", "DIFF"),
        "ONETOUCH": ("ONETOUCH", "ONE TOUCH", "TOUCH"),
        "NOTOUCH": ("NOTOUCH", "NO TOUCH"),
        "CALL": ("CALL", "HIGHER"),
        "PUT": ("PUT", "LOWER"),
        "ACCU": ("ACCU", "ACCU"),
    }
    expected_tokens = synonyms.get(expected, (expected,))
    return any(token in candidate_blob for token in expected_tokens)


def _stake_matches(record, candidate):
    expected = round(abs(_safe_float(record.get("stake"), 0.0)), 2)
    if expected <= 0.0:
        return True
    candidate_amounts = (
        candidate.get("buy_price"),
        candidate.get("amount"),
        candidate.get("amount_for"),
        candidate.get("price"),
        candidate.get("display_value"),
    )
    for raw_value in candidate_amounts:
        value = round(abs(_safe_float(raw_value, -1.0)), 2)
        if value >= 0.0 and abs(value - expected) <= 0.01:
            return True
    return False


def _symbol_matches(record, candidate):
    expected = str(record.get("symbol") or "").strip().upper()
    if not expected:
        return True
    observed = str(candidate.get("symbol") or "").strip().upper()
    if observed and observed == expected:
        return True
    blob = " ".join(
        str(candidate.get(key) or "").upper()
        for key in ("description", "display_name", "shortcode", "longcode")
    )
    return expected in blob if blob else False


def _time_matches(record, candidate, *, max_age_sec=180.0):
    submitted_at = _safe_float(record.get("submitted_at"), 0.0)
    if submitted_at <= 0.0:
        return True
    candidate_ts_values = (
        candidate.get("purchase_time"),
        candidate.get("transaction_time"),
        candidate.get("date_start"),
        candidate.get("transaction_id"),
        candidate.get("epoch"),
    )
    for raw_value in candidate_ts_values:
        ts_value = _safe_float(raw_value, 0.0)
        if ts_value <= 0.0:
            continue
        if abs(ts_value - submitted_at) <= float(max_age_sec):
            return True
    return False


def _action_looks_like_buy(candidate):
    action_blob = " ".join(
        str(candidate.get(key) or "").upper()
        for key in ("action_type", "action", "transaction_type", "description", "display_name")
    )
    if not action_blob:
        return True
    return any(token in action_blob for token in ("BUY", "PURCHASE", "OPEN"))


def _extract_portfolio_contracts(payload):
    if not isinstance(payload, dict):
        return []
    portfolio = payload.get("portfolio") if isinstance(payload.get("portfolio"), dict) else payload
    contracts = portfolio.get("contracts") if isinstance(portfolio, dict) else []
    return list(contracts or [])


def _extract_statement_transactions(payload):
    if not isinstance(payload, dict):
        return []
    statement = payload.get("statement") if isinstance(payload.get("statement"), dict) else payload
    transactions = statement.get("transactions") if isinstance(statement, dict) else []
    return list(transactions or [])


def _find_portfolio_match(record, portfolio_payload):
    candidates = []
    for contract in _extract_portfolio_contracts(portfolio_payload):
        if not isinstance(contract, dict):
            continue
        if not _symbol_matches(record, contract):
            continue
        if not _stake_matches(record, contract):
            continue
        if not _contract_type_matches(record, contract):
            continue
        if not _time_matches(record, contract):
            continue
        candidates.append(contract)
    if not candidates:
        return None
    candidates.sort(key=lambda item: _safe_float(item.get("purchase_time"), 0.0), reverse=True)
    return candidates[0]


def _find_statement_match(record, statement_payload):
    candidates = []
    for tx in _extract_statement_transactions(statement_payload):
        if not isinstance(tx, dict):
            continue
        if not _action_looks_like_buy(tx):
            continue
        if not _symbol_matches(record, tx):
            continue
        if not _stake_matches(record, tx):
            continue
        if not _contract_type_matches(record, tx):
            continue
        if not _time_matches(record, tx):
            continue
        contract_id = normalize_contract_id(tx.get("contract_id") or tx.get("reference_id"))
        if not contract_id:
            continue
        candidates.append(tx)
    if not candidates:
        return None
    candidates.sort(key=lambda item: _safe_float(item.get("transaction_time"), 0.0), reverse=True)
    return candidates[0]


def start_reconcile_batch(state, req_id_factory, *, now_ts=None, statement_limit=50):
    store = ensure_trade_execution_store(state)
    now_value = float(now_ts if now_ts is not None else time.time())
    if store.get("reconcile_waiters"):
        return None
    cooldown_until = _safe_float(store.get("reconcile_cooldown_until"), 0.0)
    if cooldown_until > now_value:
        return None
    candidates = get_records_needing_reconcile(state, now_ts=now_value)
    if not candidates:
        return None
    token = uuid.uuid4().hex
    portfolio_req_id = _normalize_req_id(req_id_factory())
    statement_req_id = _normalize_req_id(req_id_factory())
    batch = {
        "token": token,
        "created_at": now_value,
        "candidate_ids": [record.get("execution_id") for record in candidates if record.get("execution_id")],
        "portfolio_req_id": portfolio_req_id,
        "statement_req_id": statement_req_id,
        "portfolio_payload": None,
        "statement_payload": None,
    }
    store["reconcile_waiters"][portfolio_req_id] = {"token": token, "kind": "portfolio"}
    store["reconcile_waiters"][statement_req_id] = {"token": token, "kind": "statement"}
    store["reconcile_waiters"][token] = batch
    store["last_reconcile_started_at"] = now_value
    store["reconcile_cooldown_until"] = now_value + 1.5
    for record in candidates:
        record["pending_state"] = STATE_RECONCILING
        record["last_reconcile_at"] = now_value
        record["reconcile_attempts"] = int(record.get("reconcile_attempts") or 0) + 1
        record["updated_at"] = now_value
    return {
        "token": token,
        "requests": [
            {"portfolio": 1, "req_id": portfolio_req_id},
            {"statement": 1, "description": 1, "limit": int(statement_limit or 50), "req_id": statement_req_id},
        ],
    }


def _resolve_batch(store, req_id):
    safe_req_id = _normalize_req_id(req_id)
    if not safe_req_id:
        return None, None, None
    waiter = store.get("reconcile_waiters", {}).get(safe_req_id)
    if not isinstance(waiter, dict):
        return None, None, None
    token = waiter.get("token")
    kind = waiter.get("kind")
    batch = store.get("reconcile_waiters", {}).get(token)
    if not isinstance(batch, dict):
        return None, None, None
    return batch, waiter, kind


def handle_reconcile_response(state, req_id, payload, *, now_ts=None):
    store = ensure_trade_execution_store(state)
    batch, waiter, kind = _resolve_batch(store, req_id)
    if not isinstance(batch, dict):
        return None
    if kind == "portfolio":
        batch["portfolio_payload"] = _safe_json_copy(payload if isinstance(payload, dict) else {})
    elif kind == "statement":
        batch["statement_payload"] = _safe_json_copy(payload if isinstance(payload, dict) else {})
    safe_req_id = _normalize_req_id(req_id)
    if safe_req_id:
        store["reconcile_waiters"].pop(safe_req_id, None)
    if not isinstance(batch.get("portfolio_payload"), dict) or not isinstance(batch.get("statement_payload"), dict):
        return {"completed": False}

    now_value = float(now_ts if now_ts is not None else time.time())
    confirmed = []
    failed = []
    for execution_id in list(batch.get("candidate_ids") or []):
        record = _get_record_by_execution_id(store, execution_id)
        if not isinstance(record, dict):
            continue
        matched_contract = _find_portfolio_match(record, batch.get("portfolio_payload"))
        source = "portfolio"
        if not isinstance(matched_contract, dict):
            matched_contract = _find_statement_match(record, batch.get("statement_payload"))
            source = "statement"
        if isinstance(matched_contract, dict):
            contract_id = normalize_contract_id(
                matched_contract.get("contract_id") or matched_contract.get("reference_id")
            )
            if contract_id:
                mark_buy_confirmed(
                    {"trade_execution": store},
                    record.get("req_id"),
                    contract_id,
                    now_ts=now_value,
                    source=f"reconcile:{source}",
                )
                record["last_reconcile_result"] = f"confirmed:{source}"
                confirmed.append(
                    {
                        "req_id": record.get("req_id"),
                        "contract_id": contract_id,
                        "meta_snapshot": _safe_json_copy(record.get("meta_snapshot") or {}),
                        "source": source,
                    }
                )
                continue
        record["pending_state"] = STATE_FAILED
        record["updated_at"] = now_value
        record["failure_reason"] = "buy_confirmation_missing"
        record["last_reconcile_result"] = "failed:not_found"
        failed.append(
            {
                "req_id": record.get("req_id"),
                "contract_id": record.get("contract_id"),
                "meta_snapshot": _safe_json_copy(record.get("meta_snapshot") or {}),
                "reason": "buy_confirmation_missing",
            }
        )
    token = batch.get("token")
    if token:
        store["reconcile_waiters"].pop(token, None)
    store["last_reconcile_completed_at"] = now_value
    store["reconcile_cooldown_until"] = now_value + 0.5
    return {
        "completed": True,
        "confirmed": confirmed,
        "failed": failed,
    }


def snapshot_trade_execution_state(state, *, now_ts=None):
    store = ensure_trade_execution_store(state)
    now_value = float(now_ts if now_ts is not None else time.time())
    prune_trade_execution_store({"trade_execution": store}, now_ts=now_value)
    records = []
    for record in list(store.get("records", {}).values()):
        if not isinstance(record, dict):
            continue
        pending_state = str(record.get("pending_state") or "").strip().lower()
        if pending_state not in ACTIVE_STATES:
            continue
        records.append(_safe_json_copy(record))
    return {
        "version": 1,
        "records": records,
        "saved_at": now_value,
    }


def restore_trade_execution_state(state, payload, *, now_ts=None):
    if not isinstance(state, dict) or not isinstance(payload, dict):
        return []
    store = ensure_trade_execution_store(state)
    store["records"] = {}
    store["req_index"] = {}
    store["contract_index"] = {}
    store["reconcile_waiters"] = {}
    restored = []
    now_value = float(now_ts if now_ts is not None else time.time())
    for raw_record in list(payload.get("records") or []):
        if not isinstance(raw_record, dict):
            continue
        pending_state = str(raw_record.get("pending_state") or "").strip().lower()
        if pending_state not in ACTIVE_STATES:
            continue
        record = _safe_json_copy(raw_record)
        record["updated_at"] = now_value
        _store_record(store, record)
        restored.append(record)
    return restored


def iter_confirmed_contract_ids(state):
    store = ensure_trade_execution_store(state)
    contract_ids = []
    for record in list(store.get("records", {}).values()):
        if not isinstance(record, dict):
            continue
        if str(record.get("pending_state") or "").strip().lower() != STATE_CONFIRMED:
            continue
        contract_id = normalize_contract_id(record.get("contract_id"))
        if contract_id:
            contract_ids.append(contract_id)
    return contract_ids


def rebuild_meta_from_execution(record):
    if not isinstance(record, dict):
        return {}
    meta = _safe_json_copy(record.get("meta_snapshot") or {})
    if not isinstance(meta, dict):
        meta = {}
    if record.get("profile"):
        meta.setdefault("profile", record.get("profile"))
    if record.get("type") is not None:
        meta.setdefault("type", record.get("type"))
    if record.get("barrier") is not None:
        meta.setdefault("barrier", record.get("barrier"))
    if record.get("stake") is not None:
        meta.setdefault("stake", record.get("stake"))
    if record.get("symbol"):
        meta.setdefault("symbol", record.get("symbol"))
    if record.get("duration") is not None:
        meta.setdefault("duration", record.get("duration"))
    if record.get("duration_unit"):
        meta.setdefault("duration_unit", record.get("duration_unit"))
    if record.get("mode") is not None:
        meta.setdefault("mode", record.get("mode"))
    if record.get("deriv_contract_type"):
        meta.setdefault("deriv_contract_type", record.get("deriv_contract_type"))
    meta.setdefault("time", time.strftime("%H:%M:%S"))
    return meta


def describe_record(record):
    if not isinstance(record, dict):
        return {}
    return {
        "req_id": record.get("req_id"),
        "contract_id": record.get("contract_id"),
        "profile": record.get("profile"),
        "type": record.get("type"),
        "symbol": record.get("symbol"),
        "stake": record.get("stake"),
        "pending_state": record.get("pending_state"),
        "submitted_at": record.get("submitted_at"),
        "confirmed_at": record.get("confirmed_at"),
        "failure_reason": record.get("failure_reason"),
        "reconcile_attempts": record.get("reconcile_attempts"),
        "last_reconcile_result": record.get("last_reconcile_result"),
    }


def mark_trade_placed_emitted(state, *, req_id=None, contract_id=None):
    record = None
    if req_id not in (None, ""):
        record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict) and contract_id not in (None, ""):
        record = get_execution_by_contract_id(state, contract_id)
    if not isinstance(record, dict):
        return True
    already = bool(record.get("trade_placed_emitted"))
    record["trade_placed_emitted"] = True
    return not already


def mark_trade_result_emitted(state, *, req_id=None, contract_id=None):
    record = None
    if req_id not in (None, ""):
        record = get_execution_by_req_id(state, req_id)
    if not isinstance(record, dict) and contract_id not in (None, ""):
        record = get_execution_by_contract_id(state, contract_id)
    if not isinstance(record, dict):
        return True
    already = bool(record.get("trade_result_emitted"))
    record["trade_result_emitted"] = True
    return not already
