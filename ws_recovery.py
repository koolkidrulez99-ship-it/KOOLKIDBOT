from trade_execution_state import iter_confirmed_contract_ids


def collect_recovery_tick_symbols(state):
    symbols = []
    seen = set()

    def _push(raw_symbol):
        symbol = str(raw_symbol or "").strip().upper()
        if not symbol or symbol in seen:
            return
        seen.add(symbol)
        symbols.append(symbol)

    if not isinstance(state, dict):
        return symbols

    _push(state.get("current_symbol"))
    human_symbol = state.get("human_symbol") or state.get("current_symbol")
    _push(human_symbol)

    scanner = state.get("unchain_scanner") if isinstance(state.get("unchain_scanner"), dict) else {}
    if bool(scanner.get("running")):
        for symbol in list(scanner.get("symbols") or []):
            _push(symbol)

    golden = state.get("koolkid_golden_card") if isinstance(state.get("koolkid_golden_card"), dict) else {}
    if bool(golden.get("running")):
        for symbol in list(golden.get("symbols") or []):
            _push(symbol)

    return symbols


def collect_recovery_contract_ids(state):
    contract_ids = []
    seen = set()

    def _push(raw_contract_id):
        text = str(raw_contract_id or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        contract_ids.append(text)

    if not isinstance(state, dict):
        return contract_ids

    for contract_id in iter_confirmed_contract_ids(state):
        _push(contract_id)

    unchain = state.get("unchain_hl") if isinstance(state.get("unchain_hl"), dict) else {}
    for raw_entry in (unchain.get("active_contracts") or {}).values():
        if isinstance(raw_entry, dict):
            _push(raw_entry.get("contract_id"))

    ntt = state.get("ntt") if isinstance(state.get("ntt"), dict) else {}
    for raw_entry in (ntt.get("active_contracts") or {}).values():
        if isinstance(raw_entry, dict):
            _push(raw_entry.get("contract_id"))

    return contract_ids


def build_post_authorize_requests(state, *, include_balance=True):
    requests = []
    for symbol in collect_recovery_tick_symbols(state):
        requests.append({"ticks": symbol, "subscribe": 1})
    if include_balance:
        requests.append({"balance": 1, "subscribe": 1})
    for contract_id in collect_recovery_contract_ids(state):
        try:
            payload_contract_id = int(float(contract_id))
        except Exception:
            payload_contract_id = contract_id
        requests.append({"proposal_open_contract": 1, "contract_id": payload_contract_id, "subscribe": 1})
    return requests
