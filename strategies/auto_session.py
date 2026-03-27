from collections import Counter, deque
import time

from strategies.human import HumanStrategy
from strategies.jokerjoe import (
    JokerJoeStrategy,
    SEQVIX_JOKERJOE_MARKETS,
    SEQVIX_JOKERJOE_SAMPLE_SIZE,
    _seqvix_jokerjoe_refresh_market_analysis,
)
from strategies.koolkid import KoolKidStrategy
from strategies.unchain import UnchainStrategy

AUTO_SESSION_MARKETS = list(SEQVIX_JOKERJOE_MARKETS)
AUTO_SESSION_BUDGET_MIN = 1.0
AUTO_SESSION_BUDGET_MAX = 2000.0
AUTO_SESSION_FIRST_STAKE = 0.35
AUTO_SESSION_MIN_HISTORY = 100
AUTO_SESSION_HISTORY_COUNT = 120
AUTO_SESSION_CONFIDENCE_THRESHOLD = 60.0
AUTO_SESSION_RECOVERY_CONFIDENCE_THRESHOLD = 75.0
AUTO_SESSION_HIGH_CONFIDENCE_THRESHOLD = 90.0
AUTO_SESSION_MIN_BALANCE = 0.35
AUTO_SESSION_MIN_ACTION_STAKE = 0.35
AUTO_SESSION_TRADE_COOLDOWN_SEC = 1.2
AUTO_SESSION_HISTORY_BUFFER = 140

_PROFILE_DEFS = {
    "KOOLKID": {"id": "KOOLKID", "label": "KOOLKID Profile", "copy": "Scan all KOOLKID buttons"},
    "JOKERJOE": {"id": "JOKERJOE", "label": "JOKERJOE Profile", "copy": "Scan all JOKERJOE buttons"},
    "HUMAN": {"id": "HUMAN", "label": "HUMAN Profile", "copy": "Scan HUMAN Smart Assist"},
    "UNCHAIN": {"id": "UNCHAIN", "label": "UNCHAIN Profile", "copy": "Scan UNCHAIN Higher / Lower"},
}

_CANDIDATE_DEFS = {
    "KOOLKID_KIDRACKS": {"profile": "KOOLKID", "label": "KOOLKID - KidRacks", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_KOOLKIDSPEED": {"profile": "KOOLKID", "label": "KOOLKID - KoolKidSpeed", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_KOOLLUCK": {"profile": "KOOLKID", "label": "KOOLKID - KoolLuck", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_AUTO_DOLLAR": {"profile": "KOOLKID", "label": "KOOLKID - AUTO$", "kind": "digit", "dual_ok": False, "multi_leg": True},
    "KOOLKID_KIDBAGZ": {"profile": "KOOLKID", "label": "KOOLKID - KidBagz", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_MPULL": {"profile": "KOOLKID", "label": "KOOLKID - MPull", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_KIDPAIRS": {"profile": "KOOLKID", "label": "KOOLKID - KidPairs", "kind": "digit", "dual_ok": False, "multi_leg": True},
    "KOOLKID_KIDGX": {"profile": "KOOLKID", "label": "KOOLKID - kidGx", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_AI_AUTO": {"profile": "KOOLKID", "label": "KOOLKID - AI AUTO", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_OVER3": {"profile": "KOOLKID", "label": "KOOLKID - Over3 Analysis", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_KIDBRAIN": {"profile": "KOOLKID", "label": "KOOLKID - KIDBRAIN", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_EDGE_BRAIN": {"profile": "KOOLKID", "label": "KOOLKID - EDGE BRAIN", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_SMART_FLOW": {"profile": "KOOLKID", "label": "KOOLKID - SMART FLOW", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_META_AI": {"profile": "KOOLKID", "label": "KOOLKID - META AI", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_KIDRACKS_AI": {"profile": "KOOLKID", "label": "KOOLKID - KIDRACKS AI", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "KOOLKID_SEQVIX": {"profile": "KOOLKID", "label": "KOOLKID - 5VIX Sequential", "kind": "seqvix", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_SLUDGEX": {"profile": "JOKERJOE", "label": "JOKERJOE - sludgeX", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_TRIPLEX": {"profile": "JOKERJOE", "label": "JOKERJOE - tripleX", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_KIDX": {"profile": "JOKERJOE", "label": "JOKERJOE - kidX", "kind": "digit", "dual_ok": True, "multi_leg": True},
    "JOKERJOE_MULTIG": {"profile": "JOKERJOE", "label": "JOKERJOE - MultiG", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_KIDGX": {"profile": "JOKERJOE", "label": "JOKERJOE - kidGx", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_AI_AUTO": {"profile": "JOKERJOE", "label": "JOKERJOE - AI AUTO", "kind": "digit", "dual_ok": False, "multi_leg": True},
    "JOKERJOE_KIDBRAIN": {"profile": "JOKERJOE", "label": "JOKERJOE - KIDBRAIN", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_EDGE_BRAIN": {"profile": "JOKERJOE", "label": "JOKERJOE - EDGE BRAIN", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_SMART_FLOW": {"profile": "JOKERJOE", "label": "JOKERJOE - SMART FLOW", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_META_AI": {"profile": "JOKERJOE", "label": "JOKERJOE - META AI", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_KIDRACKS_AI": {"profile": "JOKERJOE", "label": "JOKERJOE - KIDRACKS AI", "kind": "digit", "dual_ok": True, "multi_leg": False},
    "JOKERJOE_SEQVIX": {"profile": "JOKERJOE", "label": "JOKERJOE - 5VIX Sequential", "kind": "seqvix", "dual_ok": True, "multi_leg": False},
    "HUMAN_RF": {"profile": "HUMAN", "label": "HUMAN - Smart Assist", "kind": "human_rf", "dual_ok": False, "multi_leg": False},
    "UNCHAIN_HIGHER": {"profile": "UNCHAIN", "label": "UNCHAIN - Higher", "kind": "unchain_hl", "dual_ok": True, "multi_leg": False},
    "UNCHAIN_LOWER": {"profile": "UNCHAIN", "label": "UNCHAIN - Lower", "kind": "unchain_hl", "dual_ok": True, "multi_leg": False},
}


def get_auto_session_catalog():
    items = []
    for key, item in _PROFILE_DEFS.items():
        row = dict(item)
        row["button_count"] = sum(1 for candidate in _CANDIDATE_DEFS.values() if candidate.get("profile") == key)
        items.append(row)
    items.sort(key=lambda row: row.get("label", ""))
    return items


def ensure_auto_session_state(state):
    session = state.get("auto_session")
    if isinstance(session, dict):
        return session
    state["auto_session"] = _new_session_state()
    return state["auto_session"]


def _new_session_state():
    return {
        "running": False,
        "token": None,
        "mode": "single",
        "selected_strategy_ids": [],
        "allowed_strategy_ids": [],
        "budget": 0.0,
        "remaining_budget": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "session_profit": 0.0,
        "recovery_mode": False,
        "wins": 0,
        "losses": 0,
        "current_stake": AUTO_SESSION_FIRST_STAKE,
        "active_market": None,
        "active_strategy": None,
        "confidence": 0.0,
        "status": "IDLE",
        "status_detail": "Ready",
        "stop_reason": None,
        "markets": {},
        "market_order": list(AUTO_SESSION_MARKETS),
        "seed_pending": set(),
        "seeded_markets": set(),
        "pending_modes": set(),
        "pending_batches": {},
        "open_contracts": {},
        "busy": False,
        "trade_index": 0,
        "batch_index": 0,
        "cooldown_until": 0.0,
        "last_action_at": 0.0,
        "last_batch": None,
        "button_stats": {},
        "events": [],
    }


def _new_dashboard_state():
    return {
        "stats": {
            "wins": 0,
            "losses": 0,
            "total_trades": 0,
            "winrate": 0.0,
            "net_pnl": 0.0,
        },
        "history": [],
    }


def ensure_auto_session_dashboard(state):
    dashboard = state.get("auto_session_dashboard")
    if isinstance(dashboard, dict):
        dashboard.setdefault("stats", {})
        dashboard.setdefault("history", [])
        return dashboard
    state["auto_session_dashboard"] = _new_dashboard_state()
    return state["auto_session_dashboard"]


def clear_auto_session_dashboard(state):
    state["auto_session_dashboard"] = _new_dashboard_state()
    return state["auto_session_dashboard"]


def get_auto_session_dashboard_payload(state, limit=40):
    dashboard = ensure_auto_session_dashboard(state)
    stats = dict(dashboard.get("stats") or {})
    history = list(dashboard.get("history") or [])
    capped_history = list(reversed(history))[: max(0, int(limit or 0))]
    return {
        "stats": {
            "wins": int(stats.get("wins", 0) or 0),
            "losses": int(stats.get("losses", 0) or 0),
            "total_trades": int(stats.get("total_trades", 0) or 0),
            "winrate": round(float(stats.get("winrate", 0.0) or 0.0), 1),
            "net_pnl": round(float(stats.get("net_pnl", 0.0) or 0.0), 2),
        },
        "history": capped_history,
    }


def reset_auto_session(state):
    state["auto_session"] = _new_session_state()
    return state["auto_session"]


def _push_event(session, text):
    text = str(text or "").strip()
    if not text:
        return
    session.setdefault("events", [])
    session["events"].append({"time": time.strftime("%H:%M:%S"), "text": text})
    if len(session["events"]) > 16:
        session["events"] = session["events"][-16:]


def _normalize_budget(value):
    try:
        amount = float(value)
    except Exception:
        amount = AUTO_SESSION_BUDGET_MIN
    amount = max(AUTO_SESSION_BUDGET_MIN, min(AUTO_SESSION_BUDGET_MAX, amount))
    return round(amount, 2)


def _normalize_nonnegative(value):
    try:
        amount = float(value)
    except Exception:
        amount = 0.0
    return round(max(0.0, amount), 2)


def _normalize_selected_strategies(primary_id, secondary_id=None):
    def normalize_profile(value, label):
        raw = str(value or "").strip().upper()
        if not raw:
            raise ValueError(f"Choose a valid {label} profile")
        if raw in _PROFILE_DEFS:
            return raw
        candidate = _CANDIDATE_DEFS.get(raw)
        if candidate:
            return str(candidate.get("profile") or "").upper().strip()
        raise ValueError(f"Choose a valid {label} profile")

    first = normalize_profile(primary_id, "primary")
    second = normalize_profile(secondary_id, "secondary") if str(secondary_id or "").strip() else ""
    if second:
        if second == first:
            raise ValueError("Choose 2 different profiles")
        return [first, second]
    return [first]


def _candidate_ids_for_profiles(profile_ids):
    wanted = {str(profile_id or "").upper().strip() for profile_id in (profile_ids or []) if str(profile_id or "").strip()}
    ordered = []
    for key, defs in _CANDIDATE_DEFS.items():
        if str(defs.get("profile") or "").upper().strip() in wanted:
            ordered.append(key)
    return ordered


def _make_market_runtime(symbol, strategy_ids):
    runtimes = {}
    for strategy_id in strategy_ids:
        runtimes[strategy_id] = {
            "strategy": _build_shadow_strategy(strategy_id),
            "last_signal": None,
            "last_confidence": 0.0,
            "last_reason": "Scanning",
            "runtime_state": {},
        }
    return {
        "symbol": symbol,
        "digits": deque(maxlen=AUTO_SESSION_HISTORY_BUFFER),
        "prices": deque(maxlen=AUTO_SESSION_HISTORY_BUFFER),
        "epochs": deque(maxlen=AUTO_SESSION_HISTORY_BUFFER),
        "ready": False,
        "last_digit": None,
        "last_price": None,
        "analysis": {},
        "candidates": runtimes,
    }


def _build_shadow_strategy(strategy_id):
    if _CANDIDATE_DEFS.get(strategy_id, {}).get("kind") == "seqvix":
        return None
    profile = _CANDIDATE_DEFS[strategy_id]["profile"]
    if profile == "KOOLKID":
        strat = KoolKidStrategy()
    elif profile == "JOKERJOE":
        strat = JokerJoeStrategy()
    elif profile == "HUMAN":
        strat = HumanStrategy()
    elif profile == "UNCHAIN":
        strat = UnchainStrategy()
    else:
        raise ValueError(f"Unsupported profile: {profile}")

    if hasattr(strat, "disable_all_autos"):
        try:
            strat.disable_all_autos()
        except Exception:
            pass
    if hasattr(strat, "tp"):
        strat.tp = 0.0
    if hasattr(strat, "sl"):
        strat.sl = 0.0
    if hasattr(strat, "auto_sl"):
        strat.auto_sl = False
    if hasattr(strat, "risk_block_reason"):
        strat.risk_block_reason = None
    if hasattr(strat, "current_auto_stake"):
        strat.current_auto_stake = AUTO_SESSION_FIRST_STAKE
    try:
        setattr(strat, "_auto_session_state", None)
    except Exception:
        pass
    return strat

def start_auto_session(state, primary_id, secondary_id=None, budget=100.0, sl=0.0, tp=0.0):
    profile_ids = _normalize_selected_strategies(primary_id, secondary_id)
    candidate_ids = _candidate_ids_for_profiles(profile_ids)
    if not candidate_ids:
        raise ValueError("No valid profile buttons are available for this session")
    session = reset_auto_session(state)
    budget = _normalize_budget(budget)
    sl = _normalize_nonnegative(sl)
    tp = _normalize_nonnegative(tp)
    mode = "dual" if len(profile_ids) == 2 else "single"

    session.update({
        "running": True,
        "token": str(int(time.time() * 1000)),
        "mode": mode,
        "selected_strategy_ids": profile_ids,
        "allowed_strategy_ids": candidate_ids,
        "budget": budget,
        "remaining_budget": budget,
        "sl": sl,
        "tp": tp,
        "session_profit": 0.0,
        "wins": 0,
        "losses": 0,
        "current_stake": AUTO_SESSION_FIRST_STAKE,
        "status": "SCANNING",
        "status_detail": "Scanning markets and profiling button setups",
        "stop_reason": None,
        "markets": {sym: _make_market_runtime(sym, candidate_ids) for sym in AUTO_SESSION_MARKETS},
        "market_order": list(AUTO_SESSION_MARKETS),
        "seed_pending": set(AUTO_SESSION_MARKETS),
        "seeded_markets": set(),
        "pending_modes": set(),
        "pending_batches": {},
        "open_contracts": {},
        "busy": False,
        "trade_index": 0,
        "batch_index": 0,
        "cooldown_until": 0.0,
        "last_action_at": 0.0,
        "last_batch": None,
        "recovery_mode": False,
        "button_stats": {},
        "events": [],
    })
    _push_event(session, "Auto Trading Session started")
    return session


def stop_auto_session(state, reason="Stopped by user"):
    session = ensure_auto_session_state(state)
    session["running"] = False
    session["busy"] = False
    session["pending_modes"] = set()
    session["pending_batches"] = {}
    session["open_contracts"] = {}
    session["stop_reason"] = str(reason or "Stopped")
    session["status"] = "STOPPED"
    session["status_detail"] = session["stop_reason"]
    _push_event(session, session["stop_reason"])
    return session


def get_auto_session_status(state):
    session = ensure_auto_session_state(state)
    selected = []
    for key in session.get("selected_strategy_ids", []) or []:
        defs = _PROFILE_DEFS.get(key)
        if not defs:
            continue
        row = dict(defs)
        row["id"] = key
        row["button_count"] = sum(1 for candidate in _CANDIDATE_DEFS.values() if candidate.get("profile") == key)
        selected.append(row)
    seeded_count = len(session.get("seeded_markets", set()) or set())
    total_markets = len(session.get("market_order", []) or AUTO_SESSION_MARKETS)
    return {
        "running": bool(session.get("running", False)),
        "mode": session.get("mode", "single"),
        "selected_strategies": selected,
        "budget": round(float(session.get("budget", 0.0) or 0.0), 2),
        "remaining_budget": round(float(session.get("remaining_budget", 0.0) or 0.0), 2),
        "current_stake": round(float(session.get("current_stake", AUTO_SESSION_FIRST_STAKE) or 0.0), 2),
        "sl": round(float(session.get("sl", 0.0) or 0.0), 2),
        "tp": round(float(session.get("tp", 0.0) or 0.0), 2),
        "active_market": session.get("active_market"),
        "active_strategy": session.get("active_strategy"),
        "confidence": round(float(session.get("confidence", 0.0) or 0.0), 1),
        "status": session.get("status", "IDLE"),
        "status_detail": session.get("status_detail", "Ready"),
        "wins": int(session.get("wins", 0) or 0),
        "losses": int(session.get("losses", 0) or 0),
        "profit_loss": round(float(session.get("session_profit", 0.0) or 0.0), 2),
        "recovery_mode": bool(session.get("recovery_mode", False)),
        "seeded_markets": seeded_count,
        "total_markets": total_markets,
        "events": list(session.get("events", []) or []),
        "last_batch": dict(session.get("last_batch") or {}),
    }


def _required_confidence(session):
    return AUTO_SESSION_RECOVERY_CONFIDENCE_THRESHOLD if bool(session.get("recovery_mode", False)) else AUTO_SESSION_CONFIDENCE_THRESHOLD


def compute_session_stake(session, live_balance, leg_count=1, confidence=None):
    legs = max(1, int(leg_count or 1))
    try:
        balance = float(live_balance or 0.0)
    except Exception:
        balance = 0.0
    remaining_budget = max(0.0, float(session.get("remaining_budget", 0.0) or 0.0))
    sl = max(0.0, float(session.get("sl", 0.0) or 0.0))
    tp = max(0.0, float(session.get("tp", 0.0) or 0.0))
    pnl = float(session.get("session_profit", 0.0) or 0.0)
    trades_done = int(session.get("trade_index", 0) or 0)
    required_confidence = _required_confidence(session)
    try:
        confidence_value = float(confidence if confidence is not None else required_confidence)
    except Exception:
        confidence_value = required_confidence

    sl_room = (sl - abs(min(0.0, pnl))) if sl > 0 else remaining_budget
    tp_room = (tp - max(0.0, pnl)) if tp > 0 else remaining_budget
    allowed = max(0.0, min(remaining_budget, max(0.0, sl_room), max(0.0, tp_room), balance))
    if allowed <= 0.0:
        return 0.0

    if trades_done <= 0:
        per_leg = AUTO_SESSION_FIRST_STAKE
    elif trades_done == 1:
        per_leg = round(max(AUTO_SESSION_FIRST_STAKE, float(session.get("budget", 0.0) or 0.0) * 0.10), 2)
    elif trades_done == 2:
        per_leg = round(max(AUTO_SESSION_FIRST_STAKE, float(session.get("budget", 0.0) or 0.0) * 0.20), 2)
    else:
        if confidence_value >= AUTO_SESSION_HIGH_CONFIDENCE_THRESHOLD:
            per_leg = round(max(AUTO_SESSION_FIRST_STAKE, remaining_budget), 2)
        elif confidence_value >= 80.0:
            per_leg = round(max(AUTO_SESSION_FIRST_STAKE, float(session.get("budget", 0.0) or 0.0) * (0.18 if bool(session.get("recovery_mode", False)) else 0.35)), 2)
        elif confidence_value >= 70.0:
            per_leg = round(max(AUTO_SESSION_FIRST_STAKE, float(session.get("budget", 0.0) or 0.0) * (0.10 if bool(session.get("recovery_mode", False)) else 0.20)), 2)
        else:
            per_leg = round(max(AUTO_SESSION_FIRST_STAKE, float(session.get("budget", 0.0) or 0.0) * (0.05 if bool(session.get("recovery_mode", False)) else 0.10)), 2)

    hard_cap = allowed / float(legs)
    per_leg = min(per_leg, hard_cap)
    if per_leg < AUTO_SESSION_MIN_ACTION_STAKE:
        return 0.0
    return round(per_leg, 2)


def feed_auto_session_history(state, symbol, prices, digit_fn):
    session = ensure_auto_session_state(state)
    if not session.get("running"):
        return
    market = (session.get("markets") or {}).get(symbol)
    if not market:
        return
    trimmed = list(prices or [])[-AUTO_SESSION_HISTORY_COUNT:]
    base_epoch = int(time.time()) - len(trimmed)
    for idx, price in enumerate(trimmed):
        digit = int(digit_fn(price))
        _feed_market_tick(session, market, symbol, price, digit, base_epoch + idx)
    market["ready"] = len(market.get("digits") or []) >= AUTO_SESSION_MIN_HISTORY
    session.setdefault("seed_pending", set()).discard(symbol)
    session.setdefault("seeded_markets", set()).add(symbol)
    _refresh_best_hint(state)


def process_auto_session_tick(state, tick, digit):
    session = ensure_auto_session_state(state)
    if not session.get("running"):
        return None

    symbol = str((tick or {}).get("symbol") or "").upper().strip()
    market = (session.get("markets") or {}).get(symbol)
    if not market:
        return None

    quote = tick.get("quote") if isinstance(tick, dict) else None
    try:
        epoch = int(float((tick or {}).get("epoch") or (tick or {}).get("timestamp") or 0))
    except Exception:
        epoch = int(time.time())
    _feed_market_tick(session, market, symbol, quote, int(digit), epoch)

    if session_should_stop(session):
        stop_auto_session(state, session.get("stop_reason") or "Session limit reached")
        return None

    if session.get("busy"):
        _refresh_best_hint(state)
        return None

    if time.time() < float(session.get("cooldown_until", 0.0) or 0.0):
        _refresh_best_hint(state)
        return None

    plan = _select_best_execution_plan(state)
    if not plan:
        return None

    _mark_plan_pending(session, plan)
    return plan


def handle_auto_session_buy_confirmed(state, contract_id, meta):
    session = ensure_auto_session_state(state)
    parsed = _parse_auto_session_mode((meta or {}).get("mode"))
    if not parsed or parsed.get("token") != session.get("token"):
        return
    mode = parsed["mode"]
    session.setdefault("pending_modes", set()).discard(mode)
    session.setdefault("open_contracts", {})[str(contract_id)] = {
        "mode": mode,
        "profile": meta.get("profile"),
        "strategy_id": parsed.get("strategy_id"),
        "batch_id": parsed.get("batch_id"),
        "stake": float(meta.get("stake", 0.0) or 0.0),
        "symbol": meta.get("symbol"),
    }
    session["busy"] = True
    session["status"] = "TRADING"
    session["status_detail"] = f"Open trade on {meta.get('symbol') or ''}".strip()


def handle_auto_session_buy_failed(state, meta, reason):
    session = ensure_auto_session_state(state)
    parsed = _parse_auto_session_mode((meta or {}).get("mode"))
    if not parsed or parsed.get("token") != session.get("token"):
        return
    mode = parsed["mode"]
    session.setdefault("pending_modes", set()).discard(mode)
    batch_id = parsed.get("batch_id")
    pending = session.setdefault("pending_batches", {}).get(batch_id)
    if pending:
        pending.setdefault("failed", 0)
        pending["failed"] += 1
    if not session.get("pending_modes") and not session.get("open_contracts"):
        session["busy"] = False
        session["cooldown_until"] = time.time() + AUTO_SESSION_TRADE_COOLDOWN_SEC
        session["status"] = "WAITING"
        session["status_detail"] = f"Last order failed: {reason}"
    _push_event(session, f"Order blocked: {reason}")


def handle_auto_session_contract_settled(state, contract, meta):
    session = ensure_auto_session_state(state)
    parsed = _parse_auto_session_mode((meta or {}).get("mode"))
    if not parsed or parsed.get("token") != session.get("token"):
        return
    contract_id = str(contract.get("contract_id"))
    session.setdefault("open_contracts", {}).pop(contract_id, None)
    try:
        profit = float(contract.get("profit", 0.0) or 0.0)
    except Exception:
        profit = 0.0
    session["session_profit"] = round(float(session.get("session_profit", 0.0) or 0.0) + profit, 2)
    strategy_id = parsed.get("strategy_id")
    button_stats = session.setdefault("button_stats", {})
    button_entry = button_stats.setdefault(strategy_id, {"wins": 0, "losses": 0, "total_trades": 0, "net_pnl": 0.0, "winrate": 0.0})
    button_entry["total_trades"] = int(button_entry.get("total_trades", 0) or 0) + 1
    button_entry["net_pnl"] = round(float(button_entry.get("net_pnl", 0.0) or 0.0) + profit, 2)
    if profit > 0:
        session["wins"] = int(session.get("wins", 0) or 0) + 1
        session["recovery_mode"] = False
        button_entry["wins"] = int(button_entry.get("wins", 0) or 0) + 1
        _push_event(session, f"Win +${profit:.2f}")
    else:
        session["losses"] = int(session.get("losses", 0) or 0) + 1
        session["recovery_mode"] = True
        button_entry["losses"] = int(button_entry.get("losses", 0) or 0) + 1
        _push_event(session, f"Loss ${profit:.2f}")
    total_button_trades = int(button_entry.get("wins", 0) or 0) + int(button_entry.get("losses", 0) or 0)
    button_entry["winrate"] = round((float(button_entry.get("wins", 0) or 0) / total_button_trades) * 100.0, 1) if total_button_trades else 0.0
    session["trade_index"] = int(session.get("trade_index", 0) or 0) + 1
    _record_auto_session_dashboard_trade(state, contract, meta, profit)
    session["remaining_budget"] = _compute_remaining_budget(session)
    if session_should_stop(session):
        stop_auto_session(state, session.get("stop_reason") or "Session target reached")
        return
    if not session.get("pending_modes") and not session.get("open_contracts"):
        session["busy"] = False
        session["cooldown_until"] = time.time() + AUTO_SESSION_TRADE_COOLDOWN_SEC
        session["status"] = "WAITING"
        session["status_detail"] = "Scanning for next high-confidence setup"
    _refresh_best_hint(state)


def session_should_stop(session):
    remaining_budget = _compute_remaining_budget(session)
    session["remaining_budget"] = remaining_budget
    pnl = float(session.get("session_profit", 0.0) or 0.0)
    sl = float(session.get("sl", 0.0) or 0.0)
    tp = float(session.get("tp", 0.0) or 0.0)
    if remaining_budget < AUTO_SESSION_MIN_BALANCE:
        session["stop_reason"] = "Budget exhausted"
        return True
    if sl > 0 and pnl <= -abs(sl):
        session["stop_reason"] = "Stop loss reached"
        return True
    if tp > 0 and pnl >= tp:
        session["stop_reason"] = "Take profit reached"
        return True
    return False


def _compute_remaining_budget(session):
    budget = max(0.0, float(session.get("budget", 0.0) or 0.0))
    pnl = float(session.get("session_profit", 0.0) or 0.0)
    loss_used = abs(min(0.0, pnl))
    return round(max(0.0, budget - loss_used), 2)


def _record_auto_session_dashboard_trade(state, contract, meta, profit):
    dashboard = ensure_auto_session_dashboard(state)
    history = dashboard.setdefault("history", [])
    stats = dashboard.setdefault("stats", {})
    parsed = _parse_auto_session_mode((meta or {}).get("mode"))
    strategy_id = parsed.get("strategy_id") if parsed else None
    button_label = _CANDIDATE_DEFS.get(strategy_id, {}).get("label")

    try:
        stake = float((meta or {}).get("stake", contract.get("buy_price", 0.0)) or 0.0)
    except Exception:
        stake = 0.0
    try:
        payout = float(contract.get("sell_price", contract.get("payout", 0.0)) or 0.0)
    except Exception:
        payout = 0.0

    result = "WIN" if float(profit or 0.0) > 0 else "LOSS"
    time_text = (
        contract.get("purchase_time")
        or contract.get("date_start")
        or contract.get("time")
        or time.strftime("%H:%M:%S")
    )

    entry = {
        "profile": str((meta or {}).get("profile") or "").upper().strip() or "AUTO_SESSION",
        "contract_id": str(contract.get("contract_id") or f"AUTO-{int(time.time() * 1000)}"),
        "time": str(time_text),
        "result": result,
        "status": result,
        "pending": False,
        "profit": round(float(profit or 0.0), 2),
        "stake": round(stake, 2),
        "payout": round(payout, 2),
        "symbol": str((meta or {}).get("symbol") or contract.get("underlying") or ""),
        "type": str((meta or {}).get("type") or contract.get("contract_type") or "TRADE"),
    }
    if strategy_id:
        entry["strategy_id"] = strategy_id
    if button_label:
        entry["button_label"] = button_label
    if (meta or {}).get("barrier") not in (None, ""):
        entry["barrier"] = (meta or {}).get("barrier")
    if (meta or {}).get("duration") not in (None, ""):
        entry["duration"] = (meta or {}).get("duration")
    if (meta or {}).get("duration_unit") not in (None, ""):
        entry["duration_unit"] = (meta or {}).get("duration_unit")

    history.append(entry)
    if len(history) > 120:
        del history[:-120]

    wins = int(stats.get("wins", 0) or 0)
    losses = int(stats.get("losses", 0) or 0)
    if result == "WIN":
        wins += 1
    else:
        losses += 1
    total = wins + losses
    net_pnl = round(float(stats.get("net_pnl", 0.0) or 0.0) + float(profit or 0.0), 2)
    stats.update({
        "wins": wins,
        "losses": losses,
        "total_trades": total,
        "winrate": round((wins / total) * 100.0, 1) if total else 0.0,
        "net_pnl": net_pnl,
    })


def _clear_stale_runtime_signal(runtime, epoch):
    state = runtime.setdefault("runtime_state", {})
    valid_epoch = state.get("ready_signal_epoch")
    if valid_epoch is not None and int(epoch) > int(valid_epoch):
        state["ready_signal"] = None
        state["ready_signal_epoch"] = None


def _update_jokerjoe_seqvix_runtime(runtime, market, epoch):
    state = runtime.setdefault("runtime_state", {})
    _clear_stale_runtime_signal(runtime, epoch)
    sample = list(market.get("digits") or [])[-SEQVIX_JOKERJOE_SAMPLE_SIZE:]
    if len(sample) < SEQVIX_JOKERJOE_SAMPLE_SIZE:
        state["armed"] = None
        state["watch_label"] = f"Scanning {len(sample)}/{SEQVIX_JOKERJOE_SAMPLE_SIZE}"
        state["analysis"] = {}
        return

    temp_market = {"buffer": list(sample)}
    analysis = _seqvix_jokerjoe_refresh_market_analysis(temp_market)
    state["analysis"] = dict(analysis)
    watch_digits = list(analysis.get("watch_digits") or [])
    watch_pct = float(analysis.get("watch_percentage", 10.0) or 10.0)
    avoid_digit = analysis.get("avoid_digit")
    avoid_text = f" avoid {int(avoid_digit)}" if avoid_digit is not None else ""
    watch_text = "/".join(str(int(d)) for d in watch_digits) if watch_digits else "-"
    state["watch_label"] = f"Watching {watch_text} ({watch_pct:.1f}%){avoid_text}".strip()

    armed = state.get("armed")
    if armed and int(epoch) > int(armed.get("epoch", -1)):
        signal_digit = int(armed.get("digit"))
        confidence = min(96.0, 60.0 + max(0.0, 10.0 - watch_pct) * 2.8 + (4.0 if len(watch_digits) == 1 else 1.5))
        state["ready_signal"] = {
            "type": "DIFFERS",
            "barrier": signal_digit,
            "duration": 1,
            "duration_unit": "t",
            "confidence": round(confidence, 1),
            "note": f"Next-tick DIFFERS {signal_digit}",
        }
        state["ready_signal_epoch"] = int(epoch)
        state["armed"] = None
        return

    current_digit = market.get("last_digit")
    if watch_digits and current_digit in watch_digits:
        state["armed"] = {
            "digit": int(current_digit),
            "epoch": int(epoch),
        }
    elif avoid_digit is not None and current_digit == avoid_digit:
        state["armed"] = None


def _best_koolkid_seqvix_signal(sample):
    counts = Counter(int(v) for v in sample if v is not None)
    total = max(1, len(sample))
    pct = {d: (counts.get(d, 0) / total) * 100.0 for d in range(10)}
    candidates = []
    for barrier in (0, 1, 2):
        losing = sum(pct[d] for d in range(0, barrier + 1))
        winning = sum(pct[d] for d in range(barrier + 1, 10))
        edge = winning - losing
        score = 56.0 + (edge * 0.65) + max(0.0, 10.0 - pct.get(barrier, 10.0)) * 1.8
        if edge > 0.25:
            candidates.append({
                "type": "OVER",
                "barrier": barrier,
                "confidence": round(min(96.0, score), 1),
                "note": f"OVER {barrier} edge {edge:.1f}",
            })
    for barrier in (7, 8, 9):
        losing = sum(pct[d] for d in range(barrier, 10))
        winning = sum(pct[d] for d in range(0, barrier))
        edge = winning - losing
        score = 56.0 + (edge * 0.65) + max(0.0, 10.0 - pct.get(barrier, 10.0)) * 1.8
        if edge > 0.25:
            candidates.append({
                "type": "UNDER",
                "barrier": barrier,
                "confidence": round(min(96.0, score), 1),
                "note": f"UNDER {barrier} edge {edge:.1f}",
            })
    if not candidates:
        return None
    return max(candidates, key=lambda row: (float(row.get("confidence", 0.0) or 0.0), -abs(int(row.get("barrier", 5)) - 5)))


def _update_koolkid_seqvix_runtime(runtime, market, epoch):
    state = runtime.setdefault("runtime_state", {})
    _clear_stale_runtime_signal(runtime, epoch)
    sample = list(market.get("digits") or [])[-30:]
    if len(sample) < 30:
        state["ready_signal"] = None
        state["ready_signal_epoch"] = None
        state["watch_label"] = f"Scanning {len(sample)}/30"
        return
    best = _best_koolkid_seqvix_signal(sample)
    if not best:
        state["ready_signal"] = None
        state["ready_signal_epoch"] = None
        state["watch_label"] = "No strong seq setup yet"
        return
    state["ready_signal"] = {
        "type": best["type"],
        "barrier": int(best["barrier"]),
        "duration": 1,
        "duration_unit": "t",
        "confidence": float(best["confidence"]),
        "note": best["note"],
    }
    state["ready_signal_epoch"] = int(epoch)
    state["watch_label"] = best["note"]


def _update_seqvix_candidate_runtime(strategy_id, runtime, market, epoch):
    if strategy_id == "JOKERJOE_SEQVIX":
        _update_jokerjoe_seqvix_runtime(runtime, market, epoch)
    elif strategy_id == "KOOLKID_SEQVIX":
        _update_koolkid_seqvix_runtime(runtime, market, epoch)


def _feed_market_tick(session, market, symbol, quote, digit, epoch):
    try:
        digit = int(digit)
    except Exception:
        return
    market["digits"].append(digit)
    market["prices"].append(quote)
    market["epochs"].append(epoch)
    market["last_digit"] = digit
    market["last_price"] = quote
    market["ready"] = len(market["digits"]) >= AUTO_SESSION_MIN_HISTORY
    market["analysis"] = _build_market_analysis(list(market["digits"]))

    fake_tick = {
        "symbol": symbol,
        "quote": quote if quote is not None else (100.0 + (digit / 100.0)),
        "epoch": epoch,
        "pip_size": 2,
    }
    for strategy_id, runtime in (market.get("candidates") or {}).items():
        if _CANDIDATE_DEFS.get(strategy_id, {}).get("kind") == "seqvix":
            _update_seqvix_candidate_runtime(strategy_id, runtime, market, epoch)
            continue
        strat = runtime.get("strategy")
        if not strat:
            continue
        try:
            if _CANDIDATE_DEFS[strategy_id]["profile"] == "HUMAN":
                strat.on_tick(fake_tick, float(fake_tick["quote"]), ts=epoch)
            else:
                strat.on_tick(fake_tick, digit)
        except Exception:
            continue


def _build_market_analysis(digits):
    window = list(digits or [])[-AUTO_SESSION_MIN_HISTORY:]
    counts = Counter(int(v) for v in window if v is not None)
    total = max(1, len(window))
    pct = {d: round((counts.get(d, 0) / total) * 100.0, 1) for d in range(10)}
    ordered_low = sorted(range(10), key=lambda d: (pct.get(d, 0.0), d))
    ordered_high = sorted(range(10), key=lambda d: (-pct.get(d, 0.0), d))
    low_sum = round(sum(pct.get(d, 0.0) for d in range(5)), 1)
    high_sum = round(sum(pct.get(d, 0.0) for d in range(5, 10)), 1)
    edge_gap = round(float(pct.get(ordered_low[1], 0.0) - pct.get(ordered_low[0], 0.0)), 1) if len(ordered_low) > 1 else 0.0
    return {
        "percentages": pct,
        "rarest_digit": ordered_low[0] if ordered_low else 0,
        "rarest_pct": float(pct.get(ordered_low[0], 0.0)) if ordered_low else 0.0,
        "second_rarest_digit": ordered_low[1] if len(ordered_low) > 1 else (ordered_low[0] if ordered_low else 0),
        "dominant_digit": ordered_high[0] if ordered_high else 0,
        "dominant_pct": float(pct.get(ordered_high[0], 0.0)) if ordered_high else 0.0,
        "edge_gap": edge_gap,
        "low_sum": low_sum,
        "high_sum": high_sum,
        "window_size": len(window),
    }


def _refresh_best_hint(state):
    session = ensure_auto_session_state(state)
    best = _select_best_execution_plan(state, preview_only=True)
    if best:
        session["active_market"] = best.get("market")
        session["active_strategy"] = best.get("label")
        session["confidence"] = round(float(best.get("confidence", 0.0) or 0.0), 1)
        if not session.get("busy"):
            if best.get("below_threshold"):
                session["status"] = "WAITING"
                session["status_detail"] = (
                    f"Best button {best.get('label')} is {float(best.get('confidence', 0.0) or 0.0):.1f}% "
                    f"(need {float(best.get('required_confidence', _required_confidence(session))):.1f}% )"
                ).replace("% )", "%)")
            else:
                session["status"] = "READY"
                session["status_detail"] = f"Best button: {best.get('label')} on {best.get('market')}"
    else:
        seeded = len(session.get("seeded_markets", set()) or set())
        total = len(session.get("market_order", []) or AUTO_SESSION_MARKETS)
        if seeded < total:
            session["status"] = "SCANNING"
            session["status_detail"] = f"Scanning markets ({seeded}/{total} ready)"
        elif not session.get("busy"):
            session["status"] = "WAITING"
            session["status_detail"] = (
                f"Scanning selected profile buttons for {_required_confidence(session):.0f}%+ confidence"
            )
        session["active_market"] = None
        session["active_strategy"] = None
        session["confidence"] = 0.0


def _profile_live_winrate(state, profile):
    strategy = ((state or {}).get("strategies") or {}).get(profile)
    if not strategy:
        return 50.0
    wins = float(getattr(strategy, "total_wins", 0) or 0)
    losses = float(getattr(strategy, "total_losses", 0) or 0)
    total = wins + losses
    if total <= 0:
        return 50.0
    return round((wins / total) * 100.0, 1)


def _button_live_score(session, strategy_id):
    button_stats = (session or {}).get("button_stats") or {}
    stats = button_stats.get(strategy_id) or {}
    total = int(stats.get("total_trades", 0) or 0)
    if total <= 0:
        return 50.0
    return round(float(stats.get("winrate", 0.0) or 0.0), 1)


def _get_unchain_session_config(state):
    root = state or {}
    config = dict((root.get("unchain_hl") or {}))
    return {
        "duration": int(config.get("duration", 5) or 5),
        "duration_unit": str(config.get("duration_unit", "t") or "t"),
        "higher_barrier": str(config.get("higher_barrier") or "+0.12"),
        "lower_barrier": str(config.get("lower_barrier") or "-0.12"),
    }


def _suggest_koolkid_barrier(snapshot):
    rarest = int(snapshot.get("rarest_digit", 5))
    return max(0, min(9, rarest))


def _suggest_koolkidspeed_barrier(snapshot):
    return 8 if float(snapshot.get("high_sum", 0.0)) >= float(snapshot.get("low_sum", 0.0)) else 2


def _configure_candidate(strategy_id, strat, market, per_trade_stake):
    snapshot = market.get("analysis") or {}
    if hasattr(strat, "disable_all_autos"):
        try:
            strat.disable_all_autos()
        except Exception:
            pass
    if hasattr(strat, "risk_block_reason"):
        strat.risk_block_reason = None
    if hasattr(strat, "current_auto_stake"):
        strat.current_auto_stake = max(AUTO_SESSION_FIRST_STAKE, float(per_trade_stake or AUTO_SESSION_FIRST_STAKE))
    if hasattr(strat, "stake"):
        try:
            strat.stake = max(AUTO_SESSION_FIRST_STAKE, float(per_trade_stake or AUTO_SESSION_FIRST_STAKE))
        except Exception:
            pass

    if strategy_id == "KOOLKID_KIDRACKS":
        strat.kidracks_barrier = _suggest_koolkid_barrier(snapshot)
    elif strategy_id == "KOOLKID_KOOLKIDSPEED":
        strat.koolkidspeed_barrier = _suggest_koolkidspeed_barrier(snapshot)
    elif strategy_id in ("KOOLKID_KIDGX", "KOOLKID_AI_AUTO"):
        strat.barrier_analysis_running = True
        strat.barrier_analysis_warm_count = max(int(getattr(strat, "barrier_analysis_warm_target", 30) or 30), len(market.get("digits") or []))
        try:
            rec = strat._get_barrier_analysis_recommended()
            if rec and rec.get("type") and rec.get("barrier") is not None:
                strat.barrier_analysis_selected = f"{str(rec['type']).upper()} {int(rec['barrier'])}"
        except Exception:
            pass
    elif strategy_id == "JOKERJOE_KIDX":
        if hasattr(strat, "kidx_barrier"):
            strat.kidx_barrier = _suggest_koolkid_barrier(snapshot)
    elif strategy_id == "JOKERJOE_KIDGX":
        if hasattr(strat, "set_kidgx_barrier"):
            try:
                strat.set_kidgx_barrier(_suggest_koolkid_barrier(snapshot))
            except Exception:
                strat.kidgx_barrier = _suggest_koolkid_barrier(snapshot)
    elif strategy_id in ("UNCHAIN_HIGHER", "UNCHAIN_LOWER"):
        try:
            strat.set_settings(
                mode="MANUAL",
                confidence_threshold=60.0,
                manual_exit_ticks=5,
                signal_strength="BALANCED",
            )
        except Exception:
            pass


def _evaluate_candidate(strategy_id, runtime, market, state, per_trade_stake, preview_only=False):
    if _CANDIDATE_DEFS.get(strategy_id, {}).get("kind") == "seqvix":
        runtime_state = runtime.setdefault("runtime_state", {})
        if not market.get("ready"):
            runtime["last_signal"] = None
            runtime["last_confidence"] = 0.0
            runtime["last_reason"] = "Warming up"
            return None
        signal = runtime_state.get("ready_signal")
        if not signal:
            runtime["last_signal"] = None
            runtime["last_confidence"] = 0.0
            runtime["last_reason"] = runtime_state.get("watch_label") or "Scanning"
            return None
        confidence = float(signal.get("confidence", 0.0) or 0.0)
        label = _CANDIDATE_DEFS[strategy_id]["label"]
        runtime["last_signal"] = signal
        runtime["last_confidence"] = confidence
        runtime["last_reason"] = runtime_state.get("watch_label") or f"Ready at {confidence:.1f}%"
        return {
            "strategy_id": strategy_id,
            "profile": _CANDIDATE_DEFS[strategy_id]["profile"],
            "label": label,
            "market": market.get("symbol"),
            "signal": signal,
            "confidence": confidence,
        }

    strat = runtime.get("strategy")
    if not strat or not market.get("ready"):
        runtime["last_signal"] = None
        runtime["last_confidence"] = 0.0
        runtime["last_reason"] = "Warming up"
        return None

    _configure_candidate(strategy_id, strat, market, per_trade_stake)
    try:
        setattr(strat, "_auto_session_state", state)
    except Exception:
        pass
    signal = _candidate_signal(strategy_id, strat)
    if not signal:
        runtime["last_signal"] = None
        runtime["last_confidence"] = 0.0
        runtime["last_reason"] = "No live setup"
        return None

    confidence = _score_signal(strategy_id, signal, strat, market, state)
    label = _CANDIDATE_DEFS[strategy_id]["label"]
    result = {"strategy_id": strategy_id, "profile": _CANDIDATE_DEFS[strategy_id]["profile"], "label": label, "market": market.get("symbol"), "signal": signal, "confidence": confidence}
    runtime["last_signal"] = signal
    runtime["last_confidence"] = confidence
    runtime["last_reason"] = f"Ready at {confidence:.1f}%"
    return result


def _candidate_signal(strategy_id, strat):
    if strategy_id in ("UNCHAIN_HIGHER", "UNCHAIN_LOWER"):
        config = _get_unchain_session_config(getattr(strat, "_auto_session_state", None))
        bias = strat.get_bias_payload(config)
        status = str((bias or {}).get("status") or "").upper().strip()
        confidence = float((bias or {}).get("shared_confidence", 0.0) or 0.0)
        duration = int(config.get("duration", 5) or 5)
        duration_unit = str(config.get("duration_unit", "t") or "t")
        if strategy_id == "UNCHAIN_HIGHER" and "HIGHER" in status:
            return {
                "type": "HIGHER",
                "barrier": config.get("higher_barrier", "+0.12"),
                "duration": duration,
                "duration_unit": duration_unit,
                "confidence": confidence,
            }
        if strategy_id == "UNCHAIN_LOWER" and "LOWER" in status:
            return {
                "type": "LOWER",
                "barrier": config.get("lower_barrier", "-0.12"),
                "duration": duration,
                "duration_unit": duration_unit,
                "confidence": confidence,
            }
        return None

    if strategy_id == "KOOLKID_KIDRACKS":
        return strat.check_kidracks_signal()
    if strategy_id == "KOOLKID_KOOLKIDSPEED":
        return strat.check_koolkidspeed_signal()
    if strategy_id == "KOOLKID_KOOLLUCK":
        strat.koolluck_auto = True
        return strat.check_koolluck_signal()
    if strategy_id == "KOOLKID_AUTO_DOLLAR":
        strat.auto_dollar_auto = True
        return strat.check_auto_dollar_signal()
    if strategy_id == "KOOLKID_KIDBAGZ":
        return strat.check_kidbagz_signal()
    if strategy_id == "KOOLKID_MPULL":
        return strat.check_mpull_signal()
    if strategy_id == "KOOLKID_KIDPAIRS":
        strat.kidpairs_trades_per_signal = 1
        return strat.check_kidpairs_signal()
    if strategy_id == "KOOLKID_KIDGX":
        strat.kidgx_auto = True
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_AI_AUTO":
        strat.ai_auto_trading = True
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_OVER3":
        return strat.check_over3_analysis_signal()
    if strategy_id == "KOOLKID_KIDBRAIN":
        if not strat.get_named_ai_modes_state().get("kidbrain"):
            strat.toggle_named_ai_mode("kidbrain")
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_EDGE_BRAIN":
        if not strat.get_named_ai_modes_state().get("edge_brain"):
            strat.toggle_named_ai_mode("edge_brain")
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_SMART_FLOW":
        if not strat.get_named_ai_modes_state().get("smart_flow"):
            strat.toggle_named_ai_mode("smart_flow")
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_META_AI":
        if not strat.get_named_ai_modes_state().get("meta_ai"):
            strat.toggle_named_ai_mode("meta_ai")
        return strat.check_auto_trade_signal()
    if strategy_id == "KOOLKID_KIDRACKS_AI":
        if not strat.get_named_ai_modes_state().get("kidracks_ai"):
            strat.toggle_named_ai_mode("kidracks_ai")
        return strat.check_auto_trade_signal()

    if strategy_id == "JOKERJOE_SLUDGEX":
        strat.auto_trade = True
        strat.sludgex_auto = True
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_TRIPLEX":
        strat.auto_trade = True
        strat.triplex_auto = True
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_KIDX":
        strat.auto_trade = True
        strat.kidx_auto = True
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_MULTIG":
        strat.multig_auto = True
        return strat.check_multig_signal()
    if strategy_id == "JOKERJOE_KIDGX":
        strat.kidgx_auto = True
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_AI_AUTO":
        strat.ai_auto_trading = True
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_KIDBRAIN":
        if not strat.get_named_ai_modes_state().get("kidbrain"):
            strat.toggle_named_ai_mode("kidbrain")
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_EDGE_BRAIN":
        if not strat.get_named_ai_modes_state().get("edge_brain"):
            strat.toggle_named_ai_mode("edge_brain")
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_SMART_FLOW":
        if not strat.get_named_ai_modes_state().get("smart_flow"):
            strat.toggle_named_ai_mode("smart_flow")
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_META_AI":
        if not strat.get_named_ai_modes_state().get("meta_ai"):
            strat.toggle_named_ai_mode("meta_ai")
        return strat.check_auto_trade_signal()
    if strategy_id == "JOKERJOE_KIDRACKS_AI":
        if not strat.get_named_ai_modes_state().get("kidracks_ai"):
            strat.toggle_named_ai_mode("kidracks_ai")
        return strat.check_auto_trade_signal()

    if strategy_id == "HUMAN_RF":
        return strat.build_human_rf_trade_signal(force_direction=None, require_threshold=True)
    return None

def _normalize_signal_list(signal):
    if signal is None:
        return []
    if isinstance(signal, list):
        return [item for item in signal if isinstance(item, dict)]
    if isinstance(signal, dict):
        return [signal]
    return []


def _score_signal(strategy_id, signal, strat, market, state):
    defs = _CANDIDATE_DEFS[strategy_id]
    snapshot = market.get("analysis") or {}
    profile_score = _profile_live_winrate(state, defs["profile"])
    button_score = _button_live_score(ensure_auto_session_state(state), strategy_id)
    signals = _normalize_signal_list(signal)
    if not signals:
        return 0.0

    if defs["kind"] == "seqvix":
        base = max(float(item.get("confidence", 0.0) or 0.0) for item in signals)
        return round(min(99.0, base * 0.68 + profile_score * 0.18 + button_score * 0.14), 1)

    if defs["kind"] == "unchain_hl":
        base = max(float(item.get("confidence", 0.0) or 0.0) for item in signals)
        return round(min(99.0, base * 0.64 + profile_score * 0.18 + button_score * 0.18), 1)

    if defs["kind"] == "human_rf":
        base = float(signal.get("confidence", 0.0) or 0.0)
        return round(min(99.0, base * 0.6 + profile_score * 0.22 + button_score * 0.18), 1)

    meta_brain = None
    try:
        meta_brain = (strat.get_ui_payload() or {}).get("meta_brain")
    except Exception:
        meta_brain = None
    if isinstance(meta_brain, dict):
        base = float(meta_brain.get("confidence_pct", 0.0) or 0.0)
        return round(min(99.0, base * 0.62 + profile_score * 0.20 + button_score * 0.18), 1)

    signal_scores = []
    for item in signals:
        ct = str(item.get("type") or item.get("contract_type") or "").upper().strip()
        barrier = item.get("barrier")
        try:
            barrier_pct = float(snapshot.get("percentages", {}).get(int(barrier), 10.0))
        except Exception:
            barrier_pct = 10.0
        rare_bonus = max(0.0, 10.0 - barrier_pct) * 2.2
        edge_bonus = max(0.0, float(snapshot.get("edge_gap", 0.0) or 0.0)) * 2.0
        side_bonus = 0.0
        if ct == "OVER":
            side_bonus = max(0.0, float(snapshot.get("high_sum", 0.0) - snapshot.get("low_sum", 0.0))) * 0.35
        elif ct == "UNDER":
            side_bonus = max(0.0, float(snapshot.get("low_sum", 0.0) - snapshot.get("high_sum", 0.0))) * 0.35
        elif ct == "DIFFERS":
            side_bonus = 6.0
        elif ct == "MATCHES":
            side_bonus = max(0.0, float(snapshot.get("dominant_pct", 0.0) or 0.0) - 10.0) * 1.1
        signal_scores.append(52.0 + rare_bonus + edge_bonus + side_bonus)
    base = max(signal_scores) if signal_scores else 0.0
    return round(min(99.0, base * 0.60 + profile_score * 0.22 + button_score * 0.18), 1)


def _select_best_execution_plan(state, preview_only=False):
    session = ensure_auto_session_state(state)
    if not session.get("running") or not session.get("markets"):
        return None

    strategy_ids = list(session.get("allowed_strategy_ids") or [])
    if not strategy_ids:
        return None

    best = None
    live_balance = float((state or {}).get("balance", 0.0) or 0.0)

    for symbol in session.get("market_order", []) or []:
        market = (session.get("markets") or {}).get(symbol)
        if not market or not market.get("ready"):
            continue

        for strategy_id in strategy_ids:
            runtime = (market.get("candidates") or {}).get(strategy_id)
            if not runtime:
                continue
            probe_stake = compute_session_stake(session, live_balance, 1, confidence=_required_confidence(session))
            result = _evaluate_candidate(strategy_id, runtime, market, state, probe_stake, preview_only=preview_only)
            if not result:
                continue
            plan = _build_plan_from_result(session, result, live_balance)
            if not plan:
                continue
            if best is None or float(plan.get("confidence", 0.0)) > float(best.get("confidence", 0.0)):
                best = plan

    if best and float(best.get("confidence", 0.0) or 0.0) < _required_confidence(session):
        if preview_only:
            best["below_threshold"] = True
            best["required_confidence"] = _required_confidence(session)
            return best
        return None
    return best


def _build_plan_from_result(session, result, live_balance):
    signals = _normalize_signal_list(result.get("signal"))
    if not signals:
        return None
    picked_signal = _pick_best_signal(signals)
    if not picked_signal:
        return None
    per_trade = compute_session_stake(session, live_balance, 1, confidence=result.get("confidence"))
    if per_trade < AUTO_SESSION_MIN_ACTION_STAKE:
        return None
    actions = _build_actions_for_signals(result, [picked_signal], per_trade)
    if not actions or _actions_conflict(actions):
        return None
    return {"market": result.get("market"), "label": result.get("label"), "strategy_ids": [result.get("strategy_id")], "confidence": float(result.get("confidence", 0.0) or 0.0), "actions": actions}


def _build_dual_plan(session, first, second, live_balance):
    first_signals = _normalize_signal_list(first.get("signal"))
    second_signals = _normalize_signal_list(second.get("signal"))
    if not first_signals or not second_signals:
        return None
    total_legs = len(first_signals) + len(second_signals)
    per_trade = compute_session_stake(session, live_balance, total_legs)
    if per_trade < AUTO_SESSION_MIN_ACTION_STAKE:
        return None
    actions = _build_actions_for_signals(first, first_signals, per_trade)
    actions.extend(_build_actions_for_signals(second, second_signals, per_trade))
    actions = _dedupe_actions(actions)
    if not actions or _actions_conflict(actions):
        return None
    combo_conf = min(99.0, ((float(first.get("confidence", 0.0)) + float(second.get("confidence", 0.0))) / 2.0) + 3.0)
    return {"market": first.get("market"), "label": f"{first.get('label')} + {second.get('label')}", "strategy_ids": [first.get("strategy_id"), second.get("strategy_id")], "confidence": combo_conf, "actions": actions}


def _build_actions_for_signals(result, signals, per_trade_stake):
    actions = []
    profile = result.get("profile")
    strategy_id = result.get("strategy_id")
    symbol = result.get("market")
    defs = _CANDIDATE_DEFS.get(strategy_id, {})
    for item in signals:
        action = {"profile": profile, "strategy_id": strategy_id, "symbol": symbol}
        if defs.get("kind") == "human_rf":
            action["kind"] = "human_rf"
            action["direction"] = str(item.get("direction") or "").upper().strip()
            action["duration"] = int(item.get("duration", 5) or 5)
            action["duration_unit"] = str(item.get("duration_unit") or "t")
            action["stake"] = round(float(per_trade_stake or AUTO_SESSION_FIRST_STAKE), 2)
        elif defs.get("kind") == "unchain_hl":
            action["kind"] = "unchain_hl"
            action["side"] = str(item.get("type") or item.get("side") or "").upper().strip()
            action["barrier"] = item.get("barrier")
            action["duration"] = int(item.get("duration", 5) or 5)
            action["duration_unit"] = str(item.get("duration_unit") or "t")
            action["stake"] = round(float(per_trade_stake or AUTO_SESSION_FIRST_STAKE), 2)
        else:
            action["kind"] = "digit"
            action["contract_type"] = str(item.get("type") or item.get("contract_type") or "").upper().strip()
            action["barrier"] = int(item.get("barrier")) if item.get("barrier") is not None else None
            action["duration"] = int(item.get("duration", 1) or 1)
            action["duration_unit"] = str(item.get("duration_unit") or "t")
            action["stake"] = round(float(per_trade_stake or AUTO_SESSION_FIRST_STAKE), 2)
        actions.append(action)
    return actions


def _pick_best_signal(signals):
    valid = [item for item in (signals or []) if isinstance(item, dict)]
    if not valid:
        return None
    ranked = sorted(
        valid,
        key=lambda item: (
            float(item.get("confidence", 0.0) or 0.0),
            1 if str(item.get("type") or item.get("contract_type") or "").upper().strip() == "DIFFERS" else 0,
            -abs(int(item.get("barrier", 5) or 5) - 5) if item.get("barrier") not in (None, "") else 0,
        ),
        reverse=True,
    )
    return ranked[0]


def _dedupe_actions(actions):
    deduped = []
    seen = set()
    for action in actions:
        key = (action.get("profile"), action.get("kind"), action.get("contract_type"), action.get("direction"), action.get("barrier"), action.get("symbol"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _actions_conflict(actions):
    normalized = list(actions or [])
    if not normalized:
        return True
    for action in normalized:
        if float(action.get("stake", 0.0) or 0.0) < AUTO_SESSION_MIN_ACTION_STAKE:
            return True
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            left = normalized[i]
            right = normalized[j]
            if left.get("symbol") != right.get("symbol"):
                continue
            if left.get("kind") != right.get("kind"):
                return True
            if left.get("kind") == "human_rf":
                if left.get("direction") != right.get("direction"):
                    return True
                continue
            l_type = str(left.get("contract_type") or "").upper()
            r_type = str(right.get("contract_type") or "").upper()
            l_bar = left.get("barrier")
            r_bar = right.get("barrier")
            if l_bar == r_bar and {l_type, r_type} in ({"MATCHES", "DIFFERS"}, {"OVER", "UNDER"}):
                return True
    return False


def _mark_plan_pending(session, plan):
    session["batch_index"] = int(session.get("batch_index", 0) or 0) + 1
    batch_id = f"B{int(session['batch_index'])}"
    token = session.get("token") or "SESSION"

    actions = []
    pending_modes = set()
    for idx, action in enumerate(plan.get("actions") or [], start=1):
        mode = f"AUTO_SESSION|{token}|{batch_id}|{action.get('strategy_id')}|{idx}|{action.get('symbol')}"
        row = dict(action)
        row["mode"] = mode
        actions.append(row)
        pending_modes.add(mode)

    session["pending_modes"] = pending_modes
    session.setdefault("pending_batches", {})[batch_id] = {"batch_id": batch_id, "market": plan.get("market"), "label": plan.get("label"), "confidence": float(plan.get("confidence", 0.0) or 0.0), "expected": len(actions), "failed": 0}
    session["busy"] = True
    session["last_action_at"] = time.time()
    session["last_batch"] = {"market": plan.get("market"), "label": plan.get("label"), "confidence": round(float(plan.get("confidence", 0.0) or 0.0), 1), "legs": len(actions)}
    session["active_market"] = plan.get("market")
    session["active_strategy"] = plan.get("label")
    session["confidence"] = round(float(plan.get("confidence", 0.0) or 0.0), 1)
    session["current_stake"] = round(min(float(action.get("stake", 0.0) or 0.0) for action in actions), 2) if actions else AUTO_SESSION_FIRST_STAKE
    session["status"] = "EXECUTING"
    session["status_detail"] = f"Submitting {len(actions)} trade(s) on {plan.get('market')}"
    _push_event(session, f"Executing {plan.get('label')} on {plan.get('market')}")
    plan["batch_id"] = batch_id
    plan["actions"] = actions


def _parse_auto_session_mode(mode):
    raw = str(mode or "").strip()
    if not raw.startswith("AUTO_SESSION|"):
        return None
    parts = raw.split("|")
    if len(parts) < 6:
        return None
    return {"mode": raw, "token": parts[1], "batch_id": parts[2], "strategy_id": parts[3], "leg_index": parts[4], "symbol": parts[5]}
