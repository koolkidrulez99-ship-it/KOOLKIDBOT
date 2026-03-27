from collections import Counter, deque
import time

from strategies.human import HumanStrategy
from strategies.jokerjoe import (
    JokerJoeStrategy,
    SEQVIX_JOKERJOE_MARKETS,
    SEQVIX_JOKERJOE_SAMPLE_SIZE,
    SEQVIX_JOKERJOE_SLOW_MARKETS,
    _seqvix_jokerjoe_refresh_market_analysis,
)
from strategies.koolkid import KoolKidStrategy
from strategies.unchain import UnchainStrategy

AUTO_SESSION_MARKETS = list(SEQVIX_JOKERJOE_MARKETS)
AUTO_SESSION_BUDGET_MIN = 1.0
AUTO_SESSION_BUDGET_MAX = 2000.0
AUTO_SESSION_FIRST_STAKE = 0.35
AUTO_SESSION_MIN_HISTORY = 30
AUTO_SESSION_HISTORY_COUNT = 40
AUTO_SESSION_CONFIDENCE_THRESHOLD = 60.0
AUTO_SESSION_CAUTION_CONFIDENCE_THRESHOLD = 68.0
AUTO_SESSION_RECOVERY_CONFIDENCE_THRESHOLD = 75.0
AUTO_SESSION_CRITICAL_CONFIDENCE_THRESHOLD = 82.0
AUTO_SESSION_MIN_BALANCE = 0.35
AUTO_SESSION_MIN_ACTION_STAKE = 0.35
AUTO_SESSION_TRADE_COOLDOWN_SEC = 1.2
AUTO_SESSION_HISTORY_BUFFER = 140
AUTO_SESSION_PENDING_TIMEOUT_SEC = 12.0
AUTO_SESSION_OPEN_CONTRACT_TIMEOUT_SEC = 180.0
AUTO_SESSION_DUAL_ROTATION_TOLERANCE = 12.0
AUTO_SESSION_SCAN_BATCH_SIZE = 5
AUTO_SESSION_SCAN_ROTATE_SEC = 3.0
AUTO_SESSION_CAUTION_RATIO = 0.80
AUTO_SESSION_BUDGET_RECOVERY_RATIO = 0.60
AUTO_SESSION_CRITICAL_RATIO = 0.40
AUTO_SESSION_CAUTION_STAKE_FACTOR = 0.85
AUTO_SESSION_RECOVERY_STAKE_FACTOR = 0.60
AUTO_SESSION_CRITICAL_STAKE_FACTOR = 0.40
AUTO_SESSION_ONE_LOSS_STAKE_FACTOR = 0.80
AUTO_SESSION_TWO_LOSS_STAKE_FACTOR = 0.65
AUTO_SESSION_THREE_LOSS_STAKE_FACTOR = 0.50
AUTO_SESSION_ONE_LOSS_COOLDOWN_SEC = 4.0
AUTO_SESSION_TWO_LOSS_COOLDOWN_SEC = 8.0
AUTO_SESSION_THREE_LOSS_COOLDOWN_SEC = 18.0
AUTO_SESSION_DEFAULT_PROFILE = "KOOLKID"

_PROFILE_DEFS = {
    "KOOLKID": {"id": "KOOLKID", "label": "KOOLKID Profile", "copy": "Scan all KOOLKID buttons"},
    "JOKERJOE": {"id": "JOKERJOE", "label": "JOKERJOE Profile", "copy": "Scan all JOKERJOE buttons"},
    "HUMAN": {"id": "HUMAN", "label": "HUMAN Profile", "copy": "Scan HUMAN Smart Assist"},
    "UNCHAIN": {"id": "UNCHAIN", "label": "UNCHAIN Profile", "copy": "Scan UNCHAIN Higher / Lower"},
}

_PROFILE_ALLOWED_MARKETS = {
    "KOOLKID": list(AUTO_SESSION_MARKETS),
    "JOKERJOE": list(SEQVIX_JOKERJOE_SLOW_MARKETS),
    "HUMAN": list(AUTO_SESSION_MARKETS),
    "UNCHAIN": list(AUTO_SESSION_MARKETS),
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
    "UNCHAIN_BOTH": {"profile": "UNCHAIN", "label": "UNCHAIN - Both", "kind": "unchain_both", "dual_ok": False, "multi_leg": True},
}


def get_auto_session_catalog():
    items = []
    for key, item in _PROFILE_DEFS.items():
        row = dict(item)
        row["button_count"] = sum(1 for candidate in _CANDIDATE_DEFS.values() if candidate.get("profile") == key)
        items.append(row)
    items.sort(key=lambda row: (0 if row.get("id") == AUTO_SESSION_DEFAULT_PROFILE else 1, row.get("label", "")))
    return items


def ensure_auto_session_state(state):
    session = state.get("auto_session")
    if isinstance(session, dict):
        if session.get("_root_state") is None:
            session["_root_state"] = state
        return session
    state["auto_session"] = _new_session_state()
    state["auto_session"]["_root_state"] = state
    return state["auto_session"]


def _new_session_state():
    return {
        "running": False,
        "_root_state": None,
        "token": None,
        "mode": "single",
        "selected_strategy_ids": [AUTO_SESSION_DEFAULT_PROFILE],
        "allowed_strategy_ids": [],
        "budget": 0.0,
        "remaining_budget": 0.0,
        "budget_used": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "protected_profit": 0.0,
        "session_profit": 0.0,
        "health_state": "NORMAL",
        "recovery_mode": False,
        "loss_streak": 0,
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
        "scan_cursor": 0,
        "scan_batch_size": AUTO_SESSION_SCAN_BATCH_SIZE,
        "last_scan_rotate_at": 0.0,
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
        "last_dual_profile": None,
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
            "protected_profit": 0.0,
            "budget_used": 0.0,
            "remaining_budget": 0.0,
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


def clear_auto_session_progress(state):
    session = ensure_auto_session_state(state)
    session["protected_profit"] = 0.0
    session["budget_used"] = 0.0
    session["session_profit"] = 0.0
    session["remaining_budget"] = round(float(session.get("budget", 0.0) or 0.0), 2)
    session["health_state"] = "NORMAL"
    session["recovery_mode"] = False
    session["loss_streak"] = 0
    session["wins"] = 0
    session["losses"] = 0
    session["current_stake"] = AUTO_SESSION_FIRST_STAKE
    session["active_market"] = None
    session["active_strategy"] = None
    session["confidence"] = 0.0
    session["stop_reason"] = None
    session["trade_index"] = 0
    session["batch_index"] = 0
    session["cooldown_until"] = 0.0
    session["last_action_at"] = 0.0
    session["last_batch"] = None
    session["last_dual_profile"] = None
    session["button_stats"] = {}
    session["events"] = []
    session["pending_modes"] = set()
    session["pending_batches"] = {}
    session["open_contracts"] = {}
    session["busy"] = False
    if session.get("running"):
        session["status"] = "SCANNING"
        session["status_detail"] = "Scanning markets and profiling button setups"
    else:
        session["status"] = "IDLE"
        session["status_detail"] = "Ready"
    return session


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
            "protected_profit": round(float(stats.get("protected_profit", 0.0) or 0.0), 2),
            "budget_used": round(float(stats.get("budget_used", 0.0) or 0.0), 2),
            "remaining_budget": round(float(stats.get("remaining_budget", 0.0) or 0.0), 2),
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


def _allowed_markets_for_profiles(profile_ids):
    selected = [
        str(profile_id or "").upper().strip()
        for profile_id in (profile_ids or [])
        if str(profile_id or "").strip()
    ]
    if not selected:
        return list(AUTO_SESSION_MARKETS)
    allowed = set()
    for profile_id in selected:
        for symbol in (_PROFILE_ALLOWED_MARKETS.get(profile_id) or AUTO_SESSION_MARKETS):
            allowed.add(str(symbol or "").upper().strip())
    ordered = [symbol for symbol in AUTO_SESSION_MARKETS if symbol in allowed]
    return ordered or list(AUTO_SESSION_MARKETS)


def _candidate_allowed_on_market(strategy_id, symbol):
    defs = _CANDIDATE_DEFS.get(strategy_id) or {}
    profile = str(defs.get("profile") or "").upper().strip()
    sym = str(symbol or "").upper().strip()
    if profile == "JOKERJOE" and sym not in SEQVIX_JOKERJOE_SLOW_MARKETS:
        return False
    return True


def _budget_ratio(session):
    budget = max(0.0, float(session.get("budget", 0.0) or 0.0))
    if budget <= 0:
        return 0.0
    return max(0.0, min(1.0, float(session.get("remaining_budget", 0.0) or 0.0) / budget))


def _health_state(session):
    ratio = _budget_ratio(session)
    if ratio < AUTO_SESSION_CRITICAL_RATIO:
        return "CRITICAL"
    if ratio < AUTO_SESSION_BUDGET_RECOVERY_RATIO:
        return "BUDGET_RECOVERY"
    if ratio < AUTO_SESSION_CAUTION_RATIO:
        return "CAUTION"
    return "NORMAL"


def _sync_session_totals(session):
    protected_profit = max(0.0, float(session.get("protected_profit", 0.0) or 0.0))
    budget_used = max(0.0, float(session.get("budget_used", 0.0) or 0.0))
    session["protected_profit"] = round(protected_profit, 2)
    session["budget_used"] = round(budget_used, 2)
    session["session_profit"] = round(protected_profit - budget_used, 2)
    session["remaining_budget"] = _compute_remaining_budget(session)
    health_state = _health_state(session)
    loss_streak = int(session.get("loss_streak", 0) or 0)
    session["health_state"] = health_state
    session["recovery_mode"] = bool(
        health_state in ("BUDGET_RECOVERY", "CRITICAL")
        or loss_streak >= 2
    )
    return session


def _scan_batch_symbols(session):
    order = list(session.get("market_order") or [])
    if not order:
        return []
    batch_size = max(1, min(int(session.get("scan_batch_size", AUTO_SESSION_SCAN_BATCH_SIZE) or AUTO_SESSION_SCAN_BATCH_SIZE), len(order)))
    cursor = int(session.get("scan_cursor", 0) or 0) % len(order)
    return [order[(cursor + idx) % len(order)] for idx in range(batch_size)]


def _maybe_rotate_scan_batch(session, now_ts=None, force=False):
    order = list(session.get("market_order") or [])
    if not order:
        return []
    batch_size = max(1, min(int(session.get("scan_batch_size", AUTO_SESSION_SCAN_BATCH_SIZE) or AUTO_SESSION_SCAN_BATCH_SIZE), len(order)))
    now_ts = float(now_ts if now_ts is not None else time.time())
    last = float(session.get("last_scan_rotate_at", 0.0) or 0.0)
    if force or last <= 0.0 or (now_ts - last) >= AUTO_SESSION_SCAN_ROTATE_SEC:
        cursor = int(session.get("scan_cursor", 0) or 0)
        if not force:
            cursor = (cursor + batch_size) % len(order)
        session["scan_cursor"] = cursor
        session["last_scan_rotate_at"] = now_ts
    return _scan_batch_symbols(session)


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
            "runtime_state": {
                "paper_stats": {"wins": 0, "losses": 0, "total_trades": 0, "winrate": 50.0},
                "paper_open": [],
                "last_paper_key": None,
            },
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
    previous_session = ensure_auto_session_state(state)
    dashboard = ensure_auto_session_dashboard(state)
    dashboard_stats = dict(dashboard.get("stats") or {})
    carried_profit = round(float(dashboard_stats.get("protected_profit", dashboard_stats.get("net_pnl", 0.0)) or 0.0), 2)
    carried_budget_used = round(float(dashboard_stats.get("budget_used", 0.0) or 0.0), 2)
    carried_wins = int(dashboard_stats.get("wins", 0) or 0)
    carried_losses = int(dashboard_stats.get("losses", 0) or 0)
    carried_total = int(dashboard_stats.get("total_trades", 0) or 0)
    carried_button_stats = {}
    carried_last_dual_profile = str(previous_session.get("last_dual_profile") or "").upper().strip() or None
    for key, value in (previous_session.get("button_stats") or {}).items():
        if isinstance(value, dict):
            carried_button_stats[key] = dict(value)
    session = reset_auto_session(state)
    budget = _normalize_budget(budget)
    sl = _normalize_nonnegative(sl)
    tp = _normalize_nonnegative(tp)
    mode = "dual" if len(profile_ids) == 2 else "single"
    allowed_markets = _allowed_markets_for_profiles(profile_ids)

    session.update({
        "running": True,
        "_root_state": state,
        "token": str(int(time.time() * 1000)),
        "mode": mode,
        "selected_strategy_ids": profile_ids,
        "allowed_strategy_ids": candidate_ids,
        "budget": budget,
        "remaining_budget": budget,
        "budget_used": carried_budget_used,
        "sl": sl,
        "tp": tp,
        "protected_profit": carried_profit,
        "session_profit": carried_profit,
        "health_state": "NORMAL",
        "wins": carried_wins,
        "losses": carried_losses,
        "current_stake": AUTO_SESSION_FIRST_STAKE,
        "status": "SCANNING",
        "status_detail": "Scanning markets and profiling button setups",
        "stop_reason": None,
        "markets": {sym: _make_market_runtime(sym, candidate_ids) for sym in allowed_markets},
        "market_order": list(allowed_markets),
        "scan_cursor": 0,
        "scan_batch_size": AUTO_SESSION_SCAN_BATCH_SIZE,
        "last_scan_rotate_at": 0.0,
        "seed_pending": set(allowed_markets),
        "seeded_markets": set(),
        "pending_modes": set(),
        "pending_batches": {},
        "open_contracts": {},
        "busy": False,
        "trade_index": carried_total,
        "batch_index": 0,
        "cooldown_until": 0.0,
        "last_action_at": 0.0,
        "last_batch": None,
        "last_dual_profile": carried_last_dual_profile,
        "recovery_mode": False,
        "loss_streak": 0,
        "button_stats": carried_button_stats,
        "events": [],
    })
    if carried_total and bool(previous_session.get("recovery_mode", False)):
        session["loss_streak"] = max(1, int(previous_session.get("loss_streak", 0) or 0))
    _sync_session_totals(session)
    _maybe_rotate_scan_batch(session, force=True)
    if session_should_stop(session):
        session["running"] = False
        session["status"] = "STOPPED"
        session["status_detail"] = session.get("stop_reason") or "Session limit reached"
        _push_event(session, session["status_detail"])
        return session
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
    if not selected and AUTO_SESSION_DEFAULT_PROFILE in _PROFILE_DEFS:
        defs = dict(_PROFILE_DEFS[AUTO_SESSION_DEFAULT_PROFILE])
        defs["id"] = AUTO_SESSION_DEFAULT_PROFILE
        defs["button_count"] = sum(1 for candidate in _CANDIDATE_DEFS.values() if candidate.get("profile") == AUTO_SESSION_DEFAULT_PROFILE)
        selected.append(defs)
    seeded_count = len(session.get("seeded_markets", set()) or set())
    total_markets = len(session.get("market_order", []) or AUTO_SESSION_MARKETS)
    return {
        "running": bool(session.get("running", False)),
        "mode": session.get("mode", "single"),
        "selected_strategies": selected,
        "budget": round(float(session.get("budget", 0.0) or 0.0), 2),
        "remaining_budget": round(float(session.get("remaining_budget", 0.0) or 0.0), 2),
        "budget_used": round(float(session.get("budget_used", 0.0) or 0.0), 2),
        "current_stake": round(float(session.get("current_stake", AUTO_SESSION_FIRST_STAKE) or 0.0), 2),
        "sl": round(float(session.get("sl", 0.0) or 0.0), 2),
        "tp": round(float(session.get("tp", 0.0) or 0.0), 2),
        "health_state": str(session.get("health_state", _health_state(session)) or "NORMAL"),
        "loss_streak": int(session.get("loss_streak", 0) or 0),
        "active_market": session.get("active_market"),
        "active_strategy": session.get("active_strategy"),
        "confidence": round(float(session.get("confidence", 0.0) or 0.0), 1),
        "status": session.get("status", "IDLE"),
        "status_detail": session.get("status_detail", "Ready"),
        "wins": int(session.get("wins", 0) or 0),
        "losses": int(session.get("losses", 0) or 0),
        "profit_loss": round(float(session.get("session_profit", 0.0) or 0.0), 2),
        "profit_bank": round(float(session.get("protected_profit", 0.0) or 0.0), 2),
        "recovery_mode": bool(session.get("recovery_mode", False)),
        "seeded_markets": seeded_count,
        "total_markets": total_markets,
        "scan_markets": _scan_batch_symbols(session),
        "events": list(session.get("events", []) or []),
        "last_batch": dict(session.get("last_batch") or {}),
    }


def _required_confidence(session):
    state = str(session.get("health_state", _health_state(session)) or "NORMAL").upper().strip()
    if state == "CRITICAL":
        base = AUTO_SESSION_CRITICAL_CONFIDENCE_THRESHOLD
    elif state == "BUDGET_RECOVERY":
        base = AUTO_SESSION_RECOVERY_CONFIDENCE_THRESHOLD
    elif state == "CAUTION":
        base = AUTO_SESSION_CAUTION_CONFIDENCE_THRESHOLD
    else:
        base = AUTO_SESSION_CONFIDENCE_THRESHOLD
    loss_streak = int(session.get("loss_streak", 0) or 0)
    if loss_streak == 1:
        base += 3.0
    elif loss_streak >= 2:
        base = max(base, AUTO_SESSION_RECOVERY_CONFIDENCE_THRESHOLD if state != "CRITICAL" else AUTO_SESSION_CRITICAL_CONFIDENCE_THRESHOLD)
    return round(min(95.0, base), 1)


def _loss_cooldown_seconds(session, was_loss=False):
    if not was_loss:
        return AUTO_SESSION_TRADE_COOLDOWN_SEC
    loss_streak = int(session.get("loss_streak", 0) or 0)
    if loss_streak >= 3:
        return AUTO_SESSION_THREE_LOSS_COOLDOWN_SEC
    if loss_streak == 2:
        return AUTO_SESSION_TWO_LOSS_COOLDOWN_SEC
    return AUTO_SESSION_ONE_LOSS_COOLDOWN_SEC


def compute_session_stake(session, live_balance, leg_count=1, confidence=None):
    legs = max(1, int(leg_count or 1))
    try:
        balance = float(live_balance or 0.0)
    except Exception:
        balance = 0.0
    remaining_budget = max(0.0, float(session.get("remaining_budget", 0.0) or 0.0))
    sl = max(0.0, float(session.get("sl", 0.0) or 0.0))
    budget = max(0.0, float(session.get("budget", 0.0) or 0.0))
    budget_used = max(0.0, float(session.get("budget_used", 0.0) or 0.0))
    trades_done = int(session.get("trade_index", 0) or 0)
    required_confidence = _required_confidence(session)
    try:
        confidence_value = float(confidence if confidence is not None else required_confidence)
    except Exception:
        confidence_value = required_confidence

    sl_room = (sl - budget_used) if sl > 0 else remaining_budget
    allowed = max(0.0, min(remaining_budget, max(0.0, sl_room), balance))
    if allowed <= 0.0:
        return 0.0
    health_state = str(session.get("health_state", _health_state(session)) or "NORMAL").upper().strip()
    loss_streak = int(session.get("loss_streak", 0) or 0)

    if trades_done <= 0:
        total_target = AUTO_SESSION_FIRST_STAKE * float(legs)
    elif trades_done == 1:
        total_target = max(AUTO_SESSION_FIRST_STAKE * float(legs), budget * 0.10)
    elif trades_done == 2:
        total_target = max(AUTO_SESSION_FIRST_STAKE * float(legs), budget * 0.20)
    else:
        if confidence_value >= 90.0:
            total_target = remaining_budget * 0.40
        elif confidence_value >= 80.0:
            total_target = remaining_budget * 0.25
        elif confidence_value >= 70.0:
            total_target = remaining_budget * 0.15
        else:
            total_target = remaining_budget * 0.10

        if health_state == "CRITICAL":
            total_target *= AUTO_SESSION_CRITICAL_STAKE_FACTOR
        elif health_state == "BUDGET_RECOVERY":
            total_target *= AUTO_SESSION_RECOVERY_STAKE_FACTOR
        elif health_state == "CAUTION":
            total_target *= AUTO_SESSION_CAUTION_STAKE_FACTOR

    if loss_streak >= 3:
        total_target *= AUTO_SESSION_THREE_LOSS_STAKE_FACTOR
    elif loss_streak == 2:
        total_target *= AUTO_SESSION_TWO_LOSS_STAKE_FACTOR
    elif loss_streak == 1:
        total_target *= AUTO_SESSION_ONE_LOSS_STAKE_FACTOR

    total_target = max(AUTO_SESSION_FIRST_STAKE * float(legs), float(total_target or 0.0))
    total_target = min(total_target, allowed)
    per_leg = round(total_target / float(legs), 2)
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
    _maybe_rotate_scan_batch(session)

    if session_should_stop(session):
        stop_auto_session(state, session.get("stop_reason") or "Session limit reached")
        return None

    _recover_stale_session_runtime(session)

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
    _discard_pending_mode(session, mode, parsed.get("batch_id"))
    session.setdefault("open_contracts", {})[str(contract_id)] = {
        "mode": mode,
        "profile": meta.get("profile"),
        "strategy_id": parsed.get("strategy_id"),
        "batch_id": parsed.get("batch_id"),
        "stake": float(meta.get("stake", 0.0) or 0.0),
        "symbol": meta.get("symbol"),
        "opened_at": time.time(),
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
    batch_id = parsed.get("batch_id")
    _discard_pending_mode(session, mode, batch_id)
    pending = session.setdefault("pending_batches", {}).get(batch_id)
    if pending:
        pending.setdefault("failed", 0)
        pending["failed"] += 1
    if _release_session_busy_if_idle(session, f"Last order failed: {reason}"):
        session["cooldown_until"] = time.time() + AUTO_SESSION_TRADE_COOLDOWN_SEC
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
    strategy_id = parsed.get("strategy_id")
    button_stats = session.setdefault("button_stats", {})
    button_entry = button_stats.setdefault(strategy_id, {"wins": 0, "losses": 0, "total_trades": 0, "net_pnl": 0.0, "winrate": 0.0})
    button_entry["total_trades"] = int(button_entry.get("total_trades", 0) or 0) + 1
    button_entry["net_pnl"] = round(float(button_entry.get("net_pnl", 0.0) or 0.0) + profit, 2)
    if profit > 0:
        session["protected_profit"] = round(float(session.get("protected_profit", 0.0) or 0.0) + profit, 2)
        session["wins"] = int(session.get("wins", 0) or 0) + 1
        session["loss_streak"] = 0
        button_entry["wins"] = int(button_entry.get("wins", 0) or 0) + 1
        _push_event(session, f"Win +${profit:.2f}")
    else:
        session["budget_used"] = round(float(session.get("budget_used", 0.0) or 0.0) + abs(profit), 2)
        session["losses"] = int(session.get("losses", 0) or 0) + 1
        session["loss_streak"] = int(session.get("loss_streak", 0) or 0) + 1
        button_entry["losses"] = int(button_entry.get("losses", 0) or 0) + 1
        _push_event(session, f"Loss ${profit:.2f}")
    total_button_trades = int(button_entry.get("wins", 0) or 0) + int(button_entry.get("losses", 0) or 0)
    button_entry["winrate"] = round((float(button_entry.get("wins", 0) or 0) / total_button_trades) * 100.0, 1) if total_button_trades else 0.0
    session["trade_index"] = int(session.get("trade_index", 0) or 0) + 1
    _sync_session_totals(session)
    _record_auto_session_dashboard_trade(state, contract, meta, profit)
    if session_should_stop(session):
        stop_auto_session(state, session.get("stop_reason") or "Session target reached")
        return
    if _release_session_busy_if_idle(session, "Scanning for next high-confidence setup"):
        session["cooldown_until"] = time.time() + _loss_cooldown_seconds(session, was_loss=(profit <= 0))
    _refresh_best_hint(state)


def session_should_stop(session):
    _sync_session_totals(session)
    remaining_budget = float(session.get("remaining_budget", 0.0) or 0.0)
    protected_profit = float(session.get("protected_profit", 0.0) or 0.0)
    budget_used = float(session.get("budget_used", 0.0) or 0.0)
    sl = float(session.get("sl", 0.0) or 0.0)
    tp = float(session.get("tp", 0.0) or 0.0)
    if remaining_budget < AUTO_SESSION_MIN_BALANCE:
        session["stop_reason"] = "Budget exhausted"
        return True
    if sl > 0 and budget_used >= abs(sl):
        session["stop_reason"] = "Stop loss reached"
        return True
    if tp > 0 and protected_profit >= tp:
        session["stop_reason"] = "Take profit reached"
        return True
    return False


def _compute_remaining_budget(session):
    budget = max(0.0, float(session.get("budget", 0.0) or 0.0))
    budget_used = max(0.0, float(session.get("budget_used", 0.0) or 0.0))
    return round(max(0.0, budget - budget_used), 2)


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
    protected_profit = round(float(stats.get("protected_profit", 0.0) or 0.0) + (float(profit or 0.0) if profit > 0 else 0.0), 2)
    budget_used = round(float(stats.get("budget_used", 0.0) or 0.0) + (abs(float(profit or 0.0)) if profit <= 0 else 0.0), 2)
    remaining_budget = round(max(0.0, float((ensure_auto_session_state(state).get("budget", 0.0) or 0.0)) - budget_used), 2)
    net_pnl = round(protected_profit - budget_used, 2)
    stats.update({
        "wins": wins,
        "losses": losses,
        "total_trades": total,
        "winrate": round((wins / total) * 100.0, 1) if total else 0.0,
        "protected_profit": protected_profit,
        "budget_used": budget_used,
        "remaining_budget": remaining_budget,
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
        if not _candidate_allowed_on_market(strategy_id, symbol):
            continue
        if _CANDIDATE_DEFS.get(strategy_id, {}).get("kind") == "seqvix":
            _update_seqvix_candidate_runtime(strategy_id, runtime, market, epoch)
            _update_candidate_background_simulation(session, market, strategy_id, runtime, epoch, quote, digit)
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
        _update_candidate_background_simulation(session, market, strategy_id, runtime, epoch, quote, digit)


def _paper_score_from_stats(stats):
    stats = stats or {}
    total = int(stats.get("total_trades", 0) or 0)
    if total <= 0:
        return 50.0
    winrate = float(stats.get("winrate", 50.0) or 50.0)
    weight = min(1.0, total / 12.0)
    return round(50.0 + ((winrate - 50.0) * weight), 1)


def _paper_signal_key(strategy_id, signal):
    item = signal or {}
    kind = str(item.get("type") or item.get("contract_type") or item.get("side") or "").upper().strip()
    barrier = str(item.get("barrier") or "")
    duration = int(item.get("duration", 1) or 1)
    duration_unit = str(item.get("duration_unit") or "t")
    return f"{strategy_id}|{kind}|{barrier}|{duration}{duration_unit}"


def _paper_duration_ticks(signal):
    item = signal or {}
    try:
        duration = int(item.get("duration", 1) or 1)
    except Exception:
        duration = 1
    unit = str(item.get("duration_unit") or "t").lower().strip()
    if unit == "t":
        return max(1, duration)
    return max(1, min(10, duration))


def _paper_leg_wins(signal, exit_digit, exit_quote):
    item = signal or {}
    signal_type = str(item.get("type") or item.get("contract_type") or item.get("side") or "").upper().strip()
    barrier = item.get("barrier")
    if signal_type == "HIGHER":
        try:
            return float(exit_quote) > float(item.get("entry_quote", exit_quote) or 0.0) + abs(float(barrier or 0.0))
        except Exception:
            return False
    if signal_type == "LOWER":
        try:
            return float(exit_quote) < float(item.get("entry_quote", exit_quote) or 0.0) - abs(float(barrier or 0.0))
        except Exception:
            return False
    try:
        barrier_digit = int(barrier)
    except Exception:
        barrier_digit = None
    if barrier_digit is None:
        return False
    if signal_type == "OVER":
        return int(exit_digit) > barrier_digit
    if signal_type == "UNDER":
        return int(exit_digit) < barrier_digit
    if signal_type == "DIFFERS":
        return int(exit_digit) != barrier_digit
    if signal_type == "MATCHES":
        return int(exit_digit) == barrier_digit
    return False


def _open_paper_trade(strategy_id, runtime, signals, epoch, quote, digit):
    runtime_state = runtime.setdefault("runtime_state", {})
    runtime_state.setdefault("paper_open", [])
    signal_key = "|".join(_paper_signal_key(strategy_id, item) for item in signals)
    runtime_state["last_paper_key"] = signal_key
    paper_entry = {
        "entry_epoch": int(epoch),
        "exit_epoch": int(epoch) + max(_paper_duration_ticks(item) for item in signals),
        "signals": [],
        "signal_key": signal_key,
    }
    for item in signals:
        copied = dict(item)
        copied["entry_digit"] = int(digit)
        copied["entry_quote"] = float(quote if quote is not None else (100.0 + (int(digit) / 100.0)))
        paper_entry["signals"].append(copied)
    runtime_state["paper_open"].append(paper_entry)


def _settle_runtime_paper_trades(runtime, epoch, quote, digit):
    runtime_state = runtime.setdefault("runtime_state", {})
    open_trades = list(runtime_state.get("paper_open") or [])
    if not open_trades:
        return
    remaining = []
    stats = runtime_state.setdefault("paper_stats", {"wins": 0, "losses": 0, "total_trades": 0, "winrate": 50.0})
    for paper in open_trades:
        if int(epoch) < int(paper.get("exit_epoch", epoch)):
            remaining.append(paper)
            continue
        signals = list(paper.get("signals") or [])
        if not signals:
            continue
        if len(signals) == 1:
            won = _paper_leg_wins(signals[0], digit, quote)
        else:
            wins = sum(1 for item in signals if _paper_leg_wins(item, digit, quote))
            won = wins == 1
        stats["total_trades"] = int(stats.get("total_trades", 0) or 0) + 1
        if won:
            stats["wins"] = int(stats.get("wins", 0) or 0) + 1
        else:
            stats["losses"] = int(stats.get("losses", 0) or 0) + 1
        total = int(stats.get("total_trades", 0) or 0)
        stats["winrate"] = round((float(stats.get("wins", 0) or 0) / total) * 100.0, 1) if total else 50.0
    runtime_state["paper_open"] = remaining


def _candidate_paper_signals(strategy_id, runtime, market, state):
    defs = _CANDIDATE_DEFS.get(strategy_id) or {}
    if defs.get("kind") == "seqvix":
        signal = (runtime.setdefault("runtime_state", {}) or {}).get("ready_signal")
        return _normalize_signal_list(signal)
    strat = runtime.get("strategy")
    if not strat:
        return []
    _configure_candidate(strategy_id, strat, market, AUTO_SESSION_FIRST_STAKE)
    try:
        setattr(strat, "_auto_session_state", state)
    except Exception:
        pass
    signal = _candidate_signal(strategy_id, strat, state, runtime=runtime, preview_only=True, market=market)
    signals = _normalize_signal_list(signal)
    if defs.get("kind") == "unchain_both" and len(signals) >= 2:
        return signals[:2]
    picked = _pick_best_signal(signals)
    return [picked] if picked else []


def _update_candidate_background_simulation(session, market, strategy_id, runtime, epoch, quote, digit):
    runtime_state = runtime.setdefault("runtime_state", {})
    _settle_runtime_paper_trades(runtime, epoch, quote, digit)
    if not market.get("ready"):
        return
    if runtime_state.get("paper_open"):
        return
    signals = _candidate_paper_signals(strategy_id, runtime, market, session.get("_root_state", session))
    if not signals:
        return
    signal_key = "|".join(_paper_signal_key(strategy_id, item) for item in signals)
    if signal_key and signal_key == runtime_state.get("last_paper_key"):
        return
    _open_paper_trade(strategy_id, runtime, signals, epoch, quote, digit)


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
    scan_batch = _scan_batch_symbols(session)
    batch_text = ", ".join(str(sym) for sym in scan_batch[:3])
    if len(scan_batch) > 3:
        batch_text += "..."
    cooldown_remaining = max(0.0, float(session.get("cooldown_until", 0.0) or 0.0) - time.time())
    if best:
        session["active_market"] = best.get("market")
        session["active_strategy"] = best.get("label")
        session["confidence"] = round(float(best.get("confidence", 0.0) or 0.0), 1)
        if not session.get("busy"):
            if cooldown_remaining > 0.0:
                session["status"] = "WAITING"
                session["status_detail"] = (
                    f"Cooling down {cooldown_remaining:.1f}s • "
                    f"{str(session.get('health_state', _health_state(session)) or 'NORMAL').replace('_', ' ')} mode"
                )
            elif best.get("below_threshold"):
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
            session["status_detail"] = f"Scanning 30-tick batches ({seeded}/{total} ready) • {batch_text or 'warming markets'}"
        elif cooldown_remaining > 0.0 and not session.get("busy"):
            session["status"] = "WAITING"
            session["status_detail"] = (
                f"Cooling down {cooldown_remaining:.1f}s • "
                f"{str(session.get('health_state', _health_state(session)) or 'NORMAL').replace('_', ' ')} mode"
            )
        elif not session.get("busy"):
            session["status"] = "WAITING"
            session["status_detail"] = (
                f"Scanning selected profile buttons for {_required_confidence(session):.0f}%+ confidence • batch {batch_text or 'rotating'}"
            )
        session["active_market"] = None
        session["active_strategy"] = None
        session["confidence"] = 0.0


def _discard_pending_mode(session, mode, batch_id=None):
    session.setdefault("pending_modes", set()).discard(mode)
    if not batch_id:
        return
    pending = session.setdefault("pending_batches", {}).get(batch_id)
    if not pending:
        return
    modes = set(pending.get("modes") or [])
    modes.discard(mode)
    if modes:
        pending["modes"] = sorted(modes)
        pending["updated_at"] = time.time()
        return
    session["pending_batches"].pop(batch_id, None)


def _release_session_busy_if_idle(session, detail):
    if session.get("pending_modes") or session.get("open_contracts"):
        session["busy"] = True
        return False
    session["busy"] = False
    session["status"] = "WAITING"
    session["status_detail"] = str(detail or "Scanning for next high-confidence setup")
    return True


def _recover_stale_session_runtime(session):
    now = time.time()
    recovered = False

    pending_batches = session.setdefault("pending_batches", {})
    stale_batches = []
    for batch_id, pending in list(pending_batches.items()):
        modes = set(pending.get("modes") or [])
        if not modes:
            pending_batches.pop(batch_id, None)
            continue
        created_at = float(
            pending.get("updated_at")
            or pending.get("created_at")
            or session.get("last_action_at", 0.0)
            or 0.0
        )
        if created_at and (now - created_at) >= AUTO_SESSION_PENDING_TIMEOUT_SEC:
            stale_batches.append((batch_id, modes))

    for batch_id, modes in stale_batches:
        session["pending_modes"] = set(session.get("pending_modes") or set()) - set(modes)
        pending_batches.pop(batch_id, None)
        recovered = True

    open_contracts = session.setdefault("open_contracts", {})
    stale_contract_ids = []
    for contract_id, info in list(open_contracts.items()):
        info = info or {}
        opened_at = float(
            info.get("opened_at")
            or info.get("updated_at")
            or session.get("last_action_at", 0.0)
            or 0.0
        )
        if opened_at and (now - opened_at) >= AUTO_SESSION_OPEN_CONTRACT_TIMEOUT_SEC:
            stale_contract_ids.append(contract_id)

    for contract_id in stale_contract_ids:
        open_contracts.pop(contract_id, None)
        recovered = True

    if session.get("busy") and not session.get("pending_modes") and not open_contracts:
        recovered = True

    if recovered:
        session["busy"] = False
        session["status"] = "WAITING"
        session["status_detail"] = "Scanning for next high-confidence setup"
        if stale_batches:
            _push_event(session, "Recovered a stale trade request and resumed scanning")
        elif stale_contract_ids:
            _push_event(session, "Recovered a stale open trade and resumed scanning")
        else:
            _push_event(session, "Recovered a stalled session and resumed scanning")
    return recovered


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


def _button_live_score(session, strategy_id, runtime=None):
    button_stats = (session or {}).get("button_stats") or {}
    stats = button_stats.get(strategy_id) or {}
    total = int(stats.get("total_trades", 0) or 0)
    live_score = round(float(stats.get("winrate", 0.0) or 0.0), 1) if total > 0 else 50.0
    if not isinstance(runtime, dict):
        return live_score
    paper_stats = (runtime.get("runtime_state") or {}).get("paper_stats") or {}
    paper_score = _paper_score_from_stats(paper_stats)
    if total <= 0:
        return paper_score
    return round((live_score * 0.45) + (paper_score * 0.55), 1)


def _button_confidence(state, session, strategy_id, runtime=None, setup_confidence=50.0):
    defs = _CANDIDATE_DEFS.get(strategy_id) or {}
    profile_score = _profile_live_winrate(state, defs.get("profile"))
    button_score = _button_live_score(session, strategy_id, runtime=runtime)
    return round(
        min(
            99.0,
            max(
                40.0,
                (float(setup_confidence or 0.0) * 0.55)
                + (button_score * 0.30)
                + (profile_score * 0.15),
            ),
        ),
        1,
    )


def _market_confidence(snapshot, symbol, profile):
    snapshot = snapshot or {}
    rare_bonus = max(0.0, 10.0 - float(snapshot.get("rarest_pct", 10.0) or 10.0)) * 2.2
    edge_bonus = max(0.0, float(snapshot.get("edge_gap", 0.0) or 0.0)) * 4.0
    imbalance = abs(float(snapshot.get("high_sum", 0.0) or 0.0) - float(snapshot.get("low_sum", 0.0) or 0.0)) * 0.5
    score = 54.0 + rare_bonus + edge_bonus + imbalance
    sym = str(symbol or "").upper().strip()
    if sym.startswith("1HZ") and str(profile or "").upper().strip() != "JOKERJOE":
        score -= 3.0
    return round(min(99.0, max(40.0, score)), 1)


def _session_modifier_score(session):
    health_state = str(session.get("health_state", _health_state(session)) or "NORMAL").upper().strip()
    if health_state == "CRITICAL":
        score = 38.0
    elif health_state == "BUDGET_RECOVERY":
        score = 45.0
    elif health_state == "CAUTION":
        score = 53.0
    else:
        score = 60.0

    loss_streak = int(session.get("loss_streak", 0) or 0)
    if loss_streak >= 3:
        score -= 18.0
    elif loss_streak == 2:
        score -= 12.0
    elif loss_streak == 1:
        score -= 6.0

    cooldown_remaining = max(0.0, float(session.get("cooldown_until", 0.0) or 0.0) - time.time())
    if cooldown_remaining > 0.0:
        score -= min(10.0, cooldown_remaining)

    if int(session.get("trade_index", 0) or 0) >= 3:
        last_action_at = float(session.get("last_action_at", 0.0) or 0.0)
        if last_action_at > 0.0 and (time.time() - last_action_at) < 6.0:
            score -= 4.0

    return round(min(95.0, max(20.0, score)), 1)


def _final_confidence_score(market_confidence, button_confidence, session_modifier):
    return round(
        min(
            99.0,
            max(
                0.0,
                (float(market_confidence or 0.0) * 0.45)
                + (float(button_confidence or 0.0) * 0.45)
                + (float(session_modifier or 0.0) * 0.10),
            ),
        ),
        1,
    )


def _get_unchain_session_config(state):
    root = state or {}
    config = dict((root.get("unchain_hl") or {}))
    return {
        "duration": int(config.get("duration", 5) or 5),
        "duration_unit": str(config.get("duration_unit", "t") or "t"),
        "higher_barrier": str(config.get("higher_barrier") or "+0.12"),
        "lower_barrier": str(config.get("lower_barrier") or "-0.12"),
    }


def _simulate_unchain_market_config(strat, runtime, state, market):
    base = _get_unchain_session_config(state)
    runtime_state = runtime.setdefault("runtime_state", {})
    cache_key = (
        str((market or {}).get("symbol") or ""),
        len((market or {}).get("prices") or []),
        str(base.get("duration")),
        str(base.get("duration_unit")),
        str(base.get("higher_barrier")),
        str(base.get("lower_barrier")),
    )
    cached = runtime_state.get("unchain_sim_cache")
    if isinstance(cached, dict) and cached.get("key") == cache_key:
        return dict(cached.get("config") or base)

    magnitudes = []
    for raw in (
        base.get("higher_barrier"),
        base.get("lower_barrier"),
        "0.06",
        "0.08",
        "0.12",
        "0.17",
        "0.22",
        "0.28",
    ):
        try:
            magnitudes.append(round(abs(float(raw)), 2))
        except Exception:
            continue
    magnitudes = sorted(set(v for v in magnitudes if v > 0.0)) or [0.12]

    best_higher = {"score": -1.0, "barrier": base.get("higher_barrier", "+0.12")}
    best_lower = {"score": -1.0, "barrier": base.get("lower_barrier", "-0.12")}
    best_both = {"score": -1.0, "higher_barrier": base.get("higher_barrier", "+0.12"), "lower_barrier": base.get("lower_barrier", "-0.12")}
    for magnitude in magnitudes:
        probe = dict(base)
        probe["higher_barrier"] = f"+{magnitude:.2f}"
        probe["lower_barrier"] = f"-{magnitude:.2f}"
        bias = strat.get_bias_payload(probe) or {}
        shared_conf = float(bias.get("shared_confidence", 0.0) or 0.0)
        status = str(bias.get("status") or "").upper().strip()
        higher_edge = max(0.0, float(bias.get("higher_pct", 50.0) or 50.0) - 50.0)
        lower_edge = max(0.0, float(bias.get("lower_pct", 50.0) or 50.0) - 50.0)
        higher_score = shared_conf + higher_edge + (5.0 if "HIGHER" in status else 0.0)
        lower_score = shared_conf + lower_edge + (5.0 if "LOWER" in status else 0.0)
        both_score = shared_conf + min(higher_edge, lower_edge)
        if higher_score > best_higher["score"]:
            best_higher = {"score": higher_score, "barrier": probe["higher_barrier"]}
        if lower_score > best_lower["score"]:
            best_lower = {"score": lower_score, "barrier": probe["lower_barrier"]}
        if both_score > best_both["score"]:
            best_both = {
                "score": both_score,
                "higher_barrier": probe["higher_barrier"],
                "lower_barrier": probe["lower_barrier"],
            }

    resolved = dict(base)
    resolved["higher_barrier"] = best_higher["barrier"]
    resolved["lower_barrier"] = best_lower["barrier"]
    resolved["both_higher_barrier"] = best_both["higher_barrier"]
    resolved["both_lower_barrier"] = best_both["lower_barrier"]
    runtime_state["unchain_sim_cache"] = {"key": cache_key, "config": dict(resolved)}
    return resolved


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
    signal = _candidate_signal(strategy_id, strat, state, runtime=runtime, preview_only=preview_only, market=market)
    if not signal:
        runtime["last_signal"] = None
        runtime["last_confidence"] = 0.0
        runtime["last_reason"] = "No live setup"
        return None

    confidence = _score_signal(strategy_id, signal, strat, market, state, runtime=runtime)
    label = _CANDIDATE_DEFS[strategy_id]["label"]
    result = {"strategy_id": strategy_id, "profile": _CANDIDATE_DEFS[strategy_id]["profile"], "label": label, "market": market.get("symbol"), "signal": signal, "confidence": confidence}
    runtime["last_signal"] = signal
    runtime["last_confidence"] = confidence
    runtime["last_reason"] = f"Ready at {confidence:.1f}%"
    return result


def _candidate_signal(strategy_id, strat, state, runtime=None, preview_only=False, market=None):
    if strategy_id in ("UNCHAIN_HIGHER", "UNCHAIN_LOWER", "UNCHAIN_BOTH"):
        config = _simulate_unchain_market_config(
            strat,
            runtime if isinstance(runtime, dict) else {},
            getattr(strat, "_auto_session_state", None),
            market or {},
        )
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
        if strategy_id == "UNCHAIN_BOTH" and confidence >= 65.0 and "NEUTRAL" not in status:
            higher_barrier = config.get("both_higher_barrier", config.get("higher_barrier", "+0.12"))
            lower_barrier = config.get("both_lower_barrier", config.get("lower_barrier", "-0.12"))
            return [
                {
                    "type": "HIGHER",
                    "barrier": higher_barrier,
                    "duration": duration,
                    "duration_unit": duration_unit,
                    "confidence": max(55.0, confidence - 4.0),
                },
                {
                    "type": "LOWER",
                    "barrier": lower_barrier,
                    "duration": duration,
                    "duration_unit": duration_unit,
                    "confidence": max(55.0, confidence - 4.0),
                },
            ]
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
        session = ensure_auto_session_state(state)
        try:
            strat.rf_conf_threshold = float(_required_confidence(session))
        except Exception:
            pass
        payload = strat.get_human_rf_payload() or {}
        signal_state = str(payload.get("signal") or "WAIT").upper().strip()
        direction = str(payload.get("trade_direction") or "").upper().strip()
        confidence = float(payload.get("confidence", 0.0) or 0.0)
        cooldown = float(payload.get("cooldown_sec", 0.0) or 0.0)
        signal_key = str(payload.get("signal_key") or f"{direction}:{signal_state}:{payload.get('reason') or ''}").strip()

        if signal_state not in ("TAKE NOW", "LATE"):
            try:
                setattr(strat, "_auto_session_consumed_signal_key", None)
            except Exception:
                pass
            return None
        if direction not in ("RISE", "FALL"):
            return None
        if confidence < float(getattr(strat, "rf_conf_threshold", _required_confidence(session)) or 0.0):
            return None
        if cooldown > 0:
            return None
        if not preview_only:
            consumed_key = str(getattr(strat, "_auto_session_consumed_signal_key", "") or "").strip()
            if signal_key and consumed_key and signal_key == consumed_key:
                return None
            try:
                setattr(strat, "_auto_session_consumed_signal_key", signal_key)
            except Exception:
                pass
        return {
            "direction": direction,
            "contract_type": "CALL" if direction == "RISE" else "PUT",
            "stake": float(getattr(strat, "stake", 1.0) or 1.0),
            "duration": int(getattr(strat, "rf_duration_ticks", 5) or 5),
            "duration_unit": "t",
            "mode": "human_rf",
            "profile": "HUMAN",
            "confidence": confidence,
            "signal_state": signal_state,
            "reason": payload.get("reason"),
            "signal_key": signal_key,
        }
    return None

def _normalize_signal_list(signal):
    if signal is None:
        return []
    if isinstance(signal, list):
        return [item for item in signal if isinstance(item, dict)]
    if isinstance(signal, dict):
        return [signal]
    return []


def _score_signal(strategy_id, signal, strat, market, state, runtime=None):
    defs = _CANDIDATE_DEFS[strategy_id]
    snapshot = market.get("analysis") or {}
    market_score = _market_confidence(snapshot, market.get("symbol"), defs.get("profile"))
    session = ensure_auto_session_state(state)
    session_modifier = _session_modifier_score(session)
    signals = _normalize_signal_list(signal)
    if not signals:
        return 0.0

    if defs["kind"] in ("seqvix", "unchain_hl", "unchain_both", "human_rf"):
        base = max(float(item.get("confidence", 0.0) or 0.0) for item in signals)
        button_score = _button_confidence(state, session, strategy_id, runtime=runtime, setup_confidence=base)
        return _final_confidence_score(market_score, button_score, session_modifier)

    meta_brain = None
    try:
        meta_brain = (strat.get_ui_payload() or {}).get("meta_brain")
    except Exception:
        meta_brain = None
    if isinstance(meta_brain, dict):
        base = float(meta_brain.get("confidence_pct", 0.0) or 0.0)
        button_score = _button_confidence(state, session, strategy_id, runtime=runtime, setup_confidence=base)
        return _final_confidence_score(market_score, button_score, session_modifier)

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
    button_score = _button_confidence(state, session, strategy_id, runtime=runtime, setup_confidence=base)
    return _final_confidence_score(market_score, button_score, session_modifier)


def _select_best_execution_plan(state, preview_only=False):
    session = ensure_auto_session_state(state)
    if not session.get("running") or not session.get("markets"):
        return None

    strategy_ids = list(session.get("allowed_strategy_ids") or [])
    if not strategy_ids:
        return None

    best = None
    best_dual = None
    best_by_profile = {}
    live_balance = float((state or {}).get("balance", 0.0) or 0.0)
    dual_mode = str(session.get("mode") or "").lower().strip() == "dual"
    selected_profiles = {
        str(profile_id or "").upper().strip()
        for profile_id in (session.get("selected_strategy_ids") or [])
        if str(profile_id or "").strip()
    }

    for symbol in _scan_batch_symbols(session):
        market = (session.get("markets") or {}).get(symbol)
        if not market or not market.get("ready"):
            continue

        market_results = []
        for strategy_id in strategy_ids:
            if not _candidate_allowed_on_market(strategy_id, symbol):
                continue
            runtime = (market.get("candidates") or {}).get(strategy_id)
            if not runtime:
                continue
            probe_stake = compute_session_stake(session, live_balance, 1, confidence=_required_confidence(session))
            result = _evaluate_candidate(strategy_id, runtime, market, state, probe_stake, preview_only=preview_only)
            if not result:
                continue
            market_results.append(result)
            plan = _build_plan_from_result(session, result, live_balance)
            if not plan:
                continue
            if _should_replace_best_plan(session, best, plan, dual_mode=dual_mode):
                best = plan
            profile_key = _plan_primary_profile(plan)
            if profile_key:
                current_profile_best = best_by_profile.get(profile_key)
                if current_profile_best is None or float(plan.get("confidence", 0.0) or 0.0) > float(current_profile_best.get("confidence", 0.0) or 0.0):
                    best_by_profile[profile_key] = plan

        if dual_mode and len(selected_profiles) >= 2 and market_results:
            for idx, first in enumerate(market_results):
                first_profile = str(first.get("profile") or "").upper().strip()
                if first_profile not in selected_profiles:
                    continue
                for second in market_results[idx + 1:]:
                    second_profile = str(second.get("profile") or "").upper().strip()
                    if second_profile not in selected_profiles or second_profile == first_profile:
                        continue
                    plan = _build_dual_plan(session, first, second, live_balance)
                    if not plan:
                        continue
                    if _should_replace_best_plan(session, best_dual, plan, dual_mode=dual_mode):
                        best_dual = plan

    fair_single = _select_fair_dual_profile_single_plan(session, best_by_profile) if dual_mode else None
    if fair_single is not None:
        best = _prefer_dual_profile_plan(session, best, fair_single)

    if best_dual is not None:
        best = _prefer_dual_profile_plan(session, best, best_dual)

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
    defs = _CANDIDATE_DEFS.get(result.get("strategy_id"), {})
    chosen_signals = signals[:2] if defs.get("kind") == "unchain_both" else [_pick_best_signal(signals)]
    chosen_signals = [item for item in chosen_signals if isinstance(item, dict)]
    if not chosen_signals:
        return None
    per_trade = compute_session_stake(session, live_balance, len(chosen_signals), confidence=result.get("confidence"))
    if per_trade < AUTO_SESSION_MIN_ACTION_STAKE:
        return None
    actions = _build_actions_for_signals(result, chosen_signals, per_trade)
    if not actions or _actions_conflict(actions):
        return None
    return {"market": result.get("market"), "label": result.get("label"), "strategy_ids": [result.get("strategy_id")], "confidence": float(result.get("confidence", 0.0) or 0.0), "actions": actions}


def _build_dual_plan(session, first, second, live_balance):
    if not first or not second:
        return None
    first_defs = _CANDIDATE_DEFS.get(first.get("strategy_id"), {})
    second_defs = _CANDIDATE_DEFS.get(second.get("strategy_id"), {})
    if not first_defs.get("dual_ok") or not second_defs.get("dual_ok"):
        return None
    if str(first.get("market") or "") != str(second.get("market") or ""):
        return None
    if str(first.get("profile") or "").upper().strip() == str(second.get("profile") or "").upper().strip():
        return None

    first_plan = _build_plan_from_result(session, first, live_balance)
    second_plan = _build_plan_from_result(session, second, live_balance)
    if not first_plan or not second_plan:
        return None

    first_conf = float(first_plan.get("confidence", 0.0) or 0.0)
    second_conf = float(second_plan.get("confidence", 0.0) or 0.0)
    support_floor = max(45.0, _required_confidence(session) - 10.0)
    if min(first_conf, second_conf) < support_floor:
        return None

    primary_plan, primary_result = _pick_dual_primary_plan(
        session,
        first,
        first_plan,
        first_conf,
        second,
        second_plan,
        second_conf,
    )
    secondary_result = second if primary_result is first else first
    support_bonus = max(3.0, min(8.0, ((min(first_conf, second_conf) - support_floor) * 0.6) + 3.0))

    combined = dict(primary_plan)
    combined["label"] = (
        f"{primary_result.get('label')} "
        f"(dual confirm: {str(secondary_result.get('profile') or '').upper().strip()})"
    )
    combined["strategy_ids"] = [primary_result.get("strategy_id"), secondary_result.get("strategy_id")]
    combined["confidence"] = round(min(99.0, max(first_conf, second_conf) + support_bonus), 1)
    combined["dual_confirm"] = str(secondary_result.get("profile") or "").upper().strip()
    return combined


def _pick_dual_primary_plan(session, first_result, first_plan, first_conf, second_result, second_plan, second_conf):
    first_profile = str(first_result.get("profile") or "").upper().strip()
    second_profile = str(second_result.get("profile") or "").upper().strip()
    last_dual_profile = str(session.get("last_dual_profile") or "").upper().strip()
    if abs(float(first_conf) - float(second_conf)) <= AUTO_SESSION_DUAL_ROTATION_TOLERANCE and last_dual_profile:
        if first_profile == last_dual_profile and second_profile != last_dual_profile:
            return second_plan, second_result
        if second_profile == last_dual_profile and first_profile != last_dual_profile:
            return first_plan, first_result
    if float(first_conf) > float(second_conf):
        return first_plan, first_result
    if float(second_conf) > float(first_conf):
        return second_plan, second_result
    if last_dual_profile:
        if first_profile == last_dual_profile and second_profile != last_dual_profile:
            return second_plan, second_result
        if second_profile == last_dual_profile and first_profile != last_dual_profile:
            return first_plan, first_result
    return first_plan, first_result


def _plan_primary_profile(plan):
    if not isinstance(plan, dict):
        return ""
    actions = list(plan.get("actions") or [])
    if actions:
        return str(actions[0].get("profile") or "").upper().strip()
    strategy_ids = list(plan.get("strategy_ids") or [])
    if strategy_ids:
        return str((_CANDIDATE_DEFS.get(strategy_ids[0]) or {}).get("profile") or "").upper().strip()
    return ""


def _should_replace_best_plan(session, current_best, candidate_plan, dual_mode=False):
    if current_best is None:
        return True
    candidate_conf = float(candidate_plan.get("confidence", 0.0) or 0.0)
    best_conf = float(current_best.get("confidence", 0.0) or 0.0)
    if candidate_conf > best_conf:
        return True
    if candidate_conf < best_conf:
        return False
    if not dual_mode:
        return False
    current_profile = _plan_primary_profile(current_best)
    candidate_profile = _plan_primary_profile(candidate_plan)
    last_dual_profile = str(session.get("last_dual_profile") or "").upper().strip()
    if candidate_profile and candidate_profile != current_profile and last_dual_profile:
        if current_profile == last_dual_profile and candidate_profile != last_dual_profile:
            return True
    return False


def _select_fair_dual_profile_single_plan(session, best_by_profile):
    selected_profiles = [
        str(profile_id or "").upper().strip()
        for profile_id in (session.get("selected_strategy_ids") or [])
        if str(profile_id or "").strip()
    ]
    available = [best_by_profile.get(profile) for profile in selected_profiles if best_by_profile.get(profile)]
    if not available:
        return None
    strongest = max(available, key=lambda plan: float(plan.get("confidence", 0.0) or 0.0))
    if len(available) < 2:
        return strongest
    last_dual_profile = str(session.get("last_dual_profile") or "").upper().strip()
    required_confidence = float(_required_confidence(session))
    qualified = [plan for plan in available if float(plan.get("confidence", 0.0) or 0.0) >= required_confidence]
    if len(qualified) < 2:
        return strongest
    if not last_dual_profile:
        return max(qualified, key=lambda plan: float(plan.get("confidence", 0.0) or 0.0))
    for plan in qualified:
        plan_profile = _plan_primary_profile(plan)
        if plan_profile and plan_profile != last_dual_profile:
            return plan
    return max(qualified, key=lambda plan: float(plan.get("confidence", 0.0) or 0.0))


def _prefer_dual_profile_plan(session, current_plan, candidate_plan):
    if candidate_plan is None:
        return current_plan
    if current_plan is None:
        return candidate_plan
    current_conf = float(current_plan.get("confidence", 0.0) or 0.0)
    candidate_conf = float(candidate_plan.get("confidence", 0.0) or 0.0)
    current_profile = _plan_primary_profile(current_plan)
    candidate_profile = _plan_primary_profile(candidate_plan)
    last_dual_profile = str(session.get("last_dual_profile") or "").upper().strip()
    required_confidence = float(_required_confidence(session))
    if (
        last_dual_profile
        and current_profile == last_dual_profile
        and candidate_profile
        and candidate_profile != last_dual_profile
        and candidate_conf >= required_confidence
    ):
        return candidate_plan
    if last_dual_profile and candidate_profile and current_profile:
        if current_profile == last_dual_profile and candidate_profile != last_dual_profile:
            if (current_conf - candidate_conf) <= AUTO_SESSION_DUAL_ROTATION_TOLERANCE:
                return candidate_plan
        if candidate_profile == last_dual_profile and current_profile != last_dual_profile:
            if (candidate_conf - current_conf) <= AUTO_SESSION_DUAL_ROTATION_TOLERANCE:
                return current_plan
    if candidate_conf > current_conf:
        return candidate_plan
    return current_plan


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
        elif defs.get("kind") in ("unchain_hl", "unchain_both"):
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
            _signal_barrier_sort_score(item),
        ),
        reverse=True,
    )
    return ranked[0]


def _signal_barrier_sort_score(item):
    barrier = (item or {}).get("barrier")
    if barrier in (None, ""):
        return 0
    try:
        return -abs(int(barrier) - 5)
    except Exception:
        try:
            text = str(barrier).strip()
            return -abs(int(float(text)) - 5)
        except Exception:
            return 0


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
    session.setdefault("pending_batches", {})[batch_id] = {
        "batch_id": batch_id,
        "market": plan.get("market"),
        "label": plan.get("label"),
        "confidence": float(plan.get("confidence", 0.0) or 0.0),
        "expected": len(actions),
        "failed": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "modes": sorted(pending_modes),
    }
    session["busy"] = True
    session["last_action_at"] = time.time()
    session["last_batch"] = {"market": plan.get("market"), "label": plan.get("label"), "confidence": round(float(plan.get("confidence", 0.0) or 0.0), 1), "legs": len(actions)}
    session["active_market"] = plan.get("market")
    session["active_strategy"] = plan.get("label")
    session["confidence"] = round(float(plan.get("confidence", 0.0) or 0.0), 1)
    session["current_stake"] = round(min(float(action.get("stake", 0.0) or 0.0) for action in actions), 2) if actions else AUTO_SESSION_FIRST_STAKE
    if str(session.get("mode") or "").lower().strip() == "dual" and actions:
        session["last_dual_profile"] = str(actions[0].get("profile") or "").upper().strip() or session.get("last_dual_profile")
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
