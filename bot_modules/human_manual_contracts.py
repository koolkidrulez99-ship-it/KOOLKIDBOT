import json
import time

import websocket

from human_profile_contracts import build_human_manual_contract_info


_HUMAN_MANUAL_CONTRACT_CACHE = {}


def fetch_human_manual_contracts_for_symbol(symbol, *, deriv_ws_url, force_refresh=False):
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None, "No market selected"

    now_ts = time.time()
    cache_key = (sym, "USD")
    cached = _HUMAN_MANUAL_CONTRACT_CACHE.get(cache_key)
    if (
        not force_refresh
        and isinstance(cached, dict)
        and (now_ts - float(cached.get("ts", 0.0) or 0.0)) < 120.0
    ):
        return cached.get("info"), cached.get("error")

    ws = None
    try:
        ws = websocket.create_connection(deriv_ws_url, timeout=8)
        ws.send(json.dumps({"contracts_for": sym, "currency": "USD"}))
        response = json.loads(ws.recv() or "{}")
        if response.get("error"):
            err = str((response.get("error") or {}).get("message") or "contracts_for failed")
            _HUMAN_MANUAL_CONTRACT_CACHE[cache_key] = {"ts": now_ts, "info": None, "error": err}
            return None, err
        available = ((response.get("contracts_for") or {}).get("available") or [])
        info = build_human_manual_contract_info(available)
        _HUMAN_MANUAL_CONTRACT_CACHE[cache_key] = {"ts": now_ts, "info": info, "error": None}
        return info, None
    except Exception as exc:
        err = str(exc)
        _HUMAN_MANUAL_CONTRACT_CACHE[cache_key] = {"ts": now_ts, "info": None, "error": err}
        return None, err
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass


def human_manual_info_has_available_actions(info):
    if not isinstance(info, dict):
        return False
    return any(bool((item or {}).get("available")) for item in info.values() if isinstance(item, dict))


def fetch_human_manual_contracts_for_state(state, *, deriv_ws_url, force_refresh=False):
    state = state or {}
    primary = str(state.get("human_symbol") or state.get("current_symbol") or "").upper().strip()
    fallback = str(state.get("current_symbol") or "").upper().strip()
    tried = []

    for symbol in [primary, fallback]:
        if not symbol or symbol in tried:
            continue
        tried.append(symbol)
        info, err = fetch_human_manual_contracts_for_symbol(
            symbol,
            deriv_ws_url=deriv_ws_url,
            force_refresh=force_refresh,
        )
        if err and symbol == fallback:
            return None, err, symbol
        if human_manual_info_has_available_actions(info) or symbol == fallback:
            return info, err, symbol
    return None, "No market selected", primary or fallback
