import hashlib

from .time_digits import now_time


def serialize_profile_trade_history_entry(profile, entry, index):
    raw = dict(entry or {}) if isinstance(entry, dict) else {}
    if not raw:
        return None
    if raw.get("hide_from_history"):
        return None
    mode_text = str(raw.get("mode") or "").lower().strip()
    if mode_text.startswith("jokerjoe_match_batch_martingale|"):
        return None
    if profile and str(profile).upper().strip() == "JOKERJOE" and raw.get("batch_id"):
        return None

    profile_name = str(profile or "").upper().strip() or "KOOLKID"
    try:
        profit_value = float(raw.get("profit", 0) or 0)
    except Exception:
        profit_value = 0.0
    try:
        stake_value = float(raw.get("stake", raw.get("buy_price", 0)) or 0)
    except Exception:
        stake_value = 0.0

    result = str(raw.get("result") or ("WIN" if profit_value > 0 else "LOSS")).upper().strip() or "LOSS"
    time_text = str(raw.get("time") or raw.get("date_start") or raw.get("purchase_time") or now_time()).strip()
    symbol = str(raw.get("symbol") or raw.get("underlying") or "").strip()
    trade_type = str(raw.get("type") or raw.get("contract_type") or "TRADE").strip()
    contract_id = raw.get("contract_id")
    if contract_id in (None, ""):
        seed = f"{profile_name}|{index}|{time_text}|{trade_type}|{symbol}|{profit_value:.2f}|{stake_value:.2f}"
        contract_id = f"SNAPSHOT-{profile_name}-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"

    snapshot = {
        "profile": profile_name,
        "contract_id": str(contract_id),
        "time": time_text,
        "result": result,
        "status": result,
        "pending": False,
        "profit": round(profit_value, 2),
        "stake": round(stake_value, 2),
        "symbol": symbol,
        "type": trade_type,
    }
    sort_ts = None
    for candidate in (
        raw.get("sell_time"),
        raw.get("exit_tick_time"),
        raw.get("date_expiry"),
        raw.get("date_start"),
        raw.get("purchase_time"),
        raw.get("entry_tick_time"),
    ):
        normalized_ts = normalize_tick_timestamp(candidate)
        if normalized_ts is None:
            continue
        if sort_ts is None or normalized_ts > sort_ts:
            sort_ts = normalized_ts
    if sort_ts is not None:
        snapshot["_sort_ts"] = float(sort_ts)
    try:
        payout_value = float(raw.get("payout", raw.get("sell_price", 0)) or 0)
    except Exception:
        payout_value = 0.0
    if payout_value:
        snapshot["payout"] = round(payout_value, 2)

    if raw.get("barrier") not in (None, ""):
        snapshot["barrier"] = raw.get("barrier")
    if raw.get("duration") not in (None, ""):
        snapshot["duration"] = raw.get("duration")
    if raw.get("duration_unit") not in (None, ""):
        snapshot["duration_unit"] = raw.get("duration_unit")
    if raw.get("exit_digit") not in (None, ""):
        snapshot["exit_digit"] = raw.get("exit_digit")
    elif raw.get("exitDigit") not in (None, ""):
        snapshot["exitDigit"] = raw.get("exitDigit")
    return snapshot


def get_profile_trade_history_snapshot(state, profile=None):
    strategies = (state or {}).get("strategies") or {}
    if profile:
        targets = [str(profile).upper().strip()]
    else:
        targets = [str(name).upper().strip() for name in strategies.keys()]

    snapshots = {}
    for prof in targets:
        strat = strategies.get(prof)
        raw_history = list(getattr(strat, "trade_history", []) or []) if strat else []
        items = []
        for idx, entry in enumerate(raw_history):
            serialized = serialize_profile_trade_history_entry(prof, entry, idx)
            if serialized:
                items.append(serialized)
        snapshots[prof] = items
    return snapshots


def normalize_tick_timestamp(value):
    try:
        raw = float(value)
    except Exception:
        return None
    if raw <= 0:
        return None
    return raw / 1000.0 if raw > 1e11 else raw
