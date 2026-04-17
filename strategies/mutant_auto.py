import json
import logging


logger = logging.getLogger(__name__)

MIN_MUTANT_AUTO_STAKE = 0.35
STEP50_INCREMENT = 0.50
MAX_MUTANT_AUTO_LADDER_STAKE = 2000.0
MARTINGALE_MULTIPLIER = 2.0


def _build_mutant_multiplier_ladder():
    ladder = []
    stake = round(MIN_MUTANT_AUTO_STAKE, 2)
    max_stake = round(MAX_MUTANT_AUTO_LADDER_STAKE, 2)
    while stake < max_stake:
        ladder.append(stake)
        stake = round(stake * MARTINGALE_MULTIPLIER, 2)
        if stake > max_stake:
            stake = max_stake
    if not ladder or ladder[-1] != max_stake:
        ladder.append(max_stake)
    return tuple(ladder)


MARTINGALE_LADDER = _build_mutant_multiplier_ladder()
STEP50_LADDER = tuple(
    round(MIN_MUTANT_AUTO_STAKE + (STEP50_INCREMENT * idx), 2)
    for idx in range(int((MAX_MUTANT_AUTO_LADDER_STAKE - MIN_MUTANT_AUTO_STAKE) / STEP50_INCREMENT) + 1)
)
MUTANT_AUTO_PHASE_IDLE = "IDLE"
MUTANT_AUTO_PHASE_REQUESTING = "REQUESTING"
MUTANT_AUTO_PHASE_LIVE = "LIVE"
MUTANT_AUTO_PHASE_SETTLING = "SETTLING"
MUTANT_AUTO_PHASE_UNKNOWN = "UNKNOWN"


def default_mutant_auto_state():
    return {
        "enabled": False,
        "barrier": "+0.12",
        "budget": 10.0,
        "selected_side": "TOUCH",
        "martingale_enabled": False,
        "step50_enabled": False,
        "current_stake": 0.0,
        "progression_step": 0,
        "pending_contract_id": None,
        "request_in_flight": False,
        "request_started_at": 0.0,
        "execution_lock": False,
        "entry_cycle_id": 0,
        "active_signal_id": None,
        "last_signal_id": None,
        "last_signal_started_at": 0.0,
        "active_side": None,
        "active_symbol": None,
        "active_stake": 0.0,
        "active_step_index": None,
        "active_next_loss_stake": 0.0,
        "last_progress_contract_id": None,
        "last_reason": "Mutant AUTO is OFF.",
        "last_decision": "OFF",
        "last_score": 0.0,
        "last_touch_pct": 0.0,
        "last_no_touch_pct": 0.0,
        "last_started_at": 0.0,
        "trade_phase": MUTANT_AUTO_PHASE_IDLE,
        "active_plan": None,
        "last_trade_result": None,
        "last_trade_contract_id": None,
        "consumed_contract_ids": [],
        "pending_settlement": None,
    }


def _safe_float(value, fallback=0.0):
    try:
        parsed = float(value)
    except Exception:
        return float(fallback)
    return parsed if parsed == parsed else float(fallback)


def _normalize_barrier_text(value, fallback="+0.12"):
    raw = str(value if value is not None else "").strip()
    if not raw:
        raw = str(fallback or "+0.12").strip() or "+0.12"
    try:
        numeric = float(raw)
    except Exception:
        try:
            numeric = float(str(fallback or "+0.12").strip())
        except Exception:
            numeric = 0.12
    return f"{numeric:+.2f}"


def _normalize_trade_phase(value):
    phase = str(value or MUTANT_AUTO_PHASE_IDLE).strip().upper()
    if phase in (
        MUTANT_AUTO_PHASE_IDLE,
        MUTANT_AUTO_PHASE_REQUESTING,
        MUTANT_AUTO_PHASE_LIVE,
        MUTANT_AUTO_PHASE_SETTLING,
        MUTANT_AUTO_PHASE_UNKNOWN,
    ):
        return phase
    return MUTANT_AUTO_PHASE_IDLE


def _normalize_contract_text(value):
    return str(value or "").strip() or None


def _normalize_consumed_contract_ids(value):
    raw_items = list(value or []) if isinstance(value, (list, tuple, set)) else []
    normalized = []
    seen = set()
    for item in raw_items:
        cid = _normalize_contract_text(item)
        if not cid or cid in seen:
            continue
        normalized.append(cid)
        seen.add(cid)
    return normalized[-50:]


def _normalize_pending_settlement(value):
    if not isinstance(value, dict):
        return None
    return {
        "ready_at": max(0.0, _safe_float(value.get("ready_at", 0.0), 0.0)),
        "won": bool(value.get("won", False)),
        "profit": round(_safe_float(value.get("profit", 0.0), 0.0), 2),
        "side": str(value.get("side") or "").strip().upper() or None,
        "contract_id": _normalize_contract_text(value.get("contract_id")),
        "contract_meta": dict(value.get("contract_meta") or {}) if isinstance(value.get("contract_meta"), dict) else {},
        "reason": str(value.get("reason") or "").strip() or None,
    }


def mutant_auto_base_stake(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    if mutant_auto_mode(safe) == "BASE":
        return round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(safe.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    return round(MIN_MUTANT_AUTO_STAKE, 2)


def _normalize_active_plan(value):
    if not isinstance(value, dict):
        return None
    plan = {
        "mode": str(value.get("mode") or "BASE").strip().upper() or "BASE",
        "mode_label": str(value.get("mode_label") or "").strip() or None,
        "step_index": 0,
        "current_stake": 0.0,
        "next_loss_stake": 0.0,
        "budget": 0.0,
        "stop_on_win": bool(value.get("stop_on_win", False)),
        "stop_on_loss": bool(value.get("stop_on_loss", False)),
        "selected_side": str(value.get("selected_side") or "").strip().upper() or None,
        "symbol": str(value.get("symbol") or "").strip().upper() or None,
        "barrier": str(value.get("barrier") or "").strip() or None,
        "contract_id": str(value.get("contract_id") or "").strip() or None,
        "request_started_at": max(0.0, _safe_float(value.get("request_started_at", 0.0), 0.0)),
    }
    try:
        plan["step_index"] = max(0, int(value.get("step_index", 0) or 0))
    except Exception:
        plan["step_index"] = 0
    plan["current_stake"] = round(max(0.0, _safe_float(value.get("current_stake", 0.0), 0.0)), 2)
    plan["next_loss_stake"] = round(max(0.0, _safe_float(value.get("next_loss_stake", 0.0), 0.0)), 2)
    plan["budget"] = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(value.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    return plan


def _build_active_plan(
    *,
    mode,
    mode_label,
    step_index,
    current_stake,
    next_loss_stake,
    budget,
    stop_on_win,
    stop_on_loss,
    selected_side=None,
    symbol=None,
    barrier=None,
    contract_id=None,
    request_started_at=0.0,
):
    return _normalize_active_plan(
        {
            "mode": mode,
            "mode_label": mode_label,
            "step_index": step_index,
            "current_stake": current_stake,
            "next_loss_stake": next_loss_stake,
            "budget": budget,
            "stop_on_win": stop_on_win,
            "stop_on_loss": stop_on_loss,
            "selected_side": selected_side,
            "symbol": symbol,
            "barrier": barrier,
            "contract_id": contract_id,
            "request_started_at": request_started_at,
        }
    )


def _resolve_active_plan(auto, contract_meta=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    trade_plan = build_mutant_auto_trade_plan(safe)
    plan = _normalize_active_plan(safe.get("active_plan")) or _build_active_plan(
        mode=trade_plan.get("mode") or mutant_auto_mode(safe),
        mode_label=trade_plan.get("mode_label") or mutant_auto_mode_label(safe),
        step_index=trade_plan.get("step_index", safe.get("progression_step", 0) or 0),
        current_stake=trade_plan.get("current_stake") or mutant_auto_current_stake(safe),
        next_loss_stake=trade_plan.get("next_loss_stake") or mutant_auto_next_loss_stake(safe),
        budget=trade_plan.get("budget") or safe.get("budget", MIN_MUTANT_AUTO_STAKE),
        stop_on_win=trade_plan.get("stop_on_win"),
        stop_on_loss=trade_plan.get("stop_on_loss"),
        selected_side=safe.get("active_side") or safe.get("selected_side"),
        symbol=safe.get("active_symbol"),
        barrier=safe.get("barrier"),
        contract_id=safe.get("pending_contract_id"),
        request_started_at=safe.get("request_started_at", 0.0),
    )
    meta = contract_meta if isinstance(contract_meta, dict) else {}
    if meta:
        meta_mode = str(meta.get("auto_mode") or plan.get("mode") or "BASE").strip().upper() or "BASE"
        meta_mode_label = str(meta.get("auto_mode_label") or plan.get("mode_label") or mutant_auto_mode_label(safe)).strip() or None
        try:
            meta_step_index = max(0, int(meta.get("auto_step_index", plan.get("step_index", 0)) or 0))
        except Exception:
            meta_step_index = max(0, int(plan.get("step_index", 0) or 0))
        meta_current_stake = round(
            max(
                0.0,
                _safe_float(
                    meta.get("auto_current_stake"),
                    plan.get("current_stake", safe.get("active_stake", safe.get("current_stake", MIN_MUTANT_AUTO_STAKE))),
                ),
            ),
            2,
        )
        meta_next_loss_stake = round(
            max(
                0.0,
                _safe_float(
                    meta.get("auto_next_loss_stake"),
                    plan.get("next_loss_stake", mutant_auto_next_loss_stake(safe, step_index=meta_step_index)),
                ),
            ),
            2,
        )
        plan = _build_active_plan(
            mode=meta_mode,
            mode_label=meta_mode_label,
            step_index=meta_step_index,
            current_stake=meta_current_stake,
            next_loss_stake=meta_next_loss_stake,
            budget=_safe_float(meta.get("auto_budget"), plan.get("budget", safe.get("budget", MIN_MUTANT_AUTO_STAKE))),
            stop_on_win=bool(meta.get("auto_stop_on_win", plan.get("stop_on_win"))),
            stop_on_loss=bool(meta.get("auto_stop_on_loss", plan.get("stop_on_loss"))),
            selected_side=meta.get("auto_selected_side") or meta.get("type") or plan.get("selected_side"),
            symbol=meta.get("symbol") or plan.get("symbol"),
            barrier=meta.get("auto_barrier") or meta.get("barrier") or plan.get("barrier"),
            contract_id=meta.get("contract_id") or plan.get("contract_id"),
            request_started_at=meta.get("request_started_at", plan.get("request_started_at", 0.0)),
        )
    return plan


def _debug_snapshot(auto, **extra):
    safe = ensure_mutant_auto_state({"auto": auto})
    plan = _normalize_active_plan(safe.get("active_plan"))
    next_calculated_stake = extra.pop("next_calculated_stake", None)
    if next_calculated_stake is None:
        next_calculated_stake = (plan or {}).get("next_loss_stake")
        if next_calculated_stake in (None, 0, 0.0):
            next_calculated_stake = mutant_auto_next_loss_stake(safe)
    return {
        "martingale_enabled": bool(safe.get("martingale_enabled", False)),
        "martingale_step": int(safe.get("progression_step", 0) or 0),
        "base_stake": round(mutant_auto_base_stake(safe), 2),
        "current_stake": round(mutant_auto_current_stake(safe), 2),
        "last_trade_result": safe.get("last_trade_result"),
        "next_calculated_stake": round(max(0.0, _safe_float(next_calculated_stake, 0.0)), 2),
        "websocket_reconnect": bool(extra.pop("websocket_reconnect", False)),
        "martingale_state_reset": bool(extra.pop("martingale_state_reset", False)),
        "trade_phase": _normalize_trade_phase(safe.get("trade_phase")),
        "consumed_contracts": len(safe.get("consumed_contract_ids") or []),
        "settle_pending": bool(safe.get("pending_settlement")),
        **extra,
    }


def log_mutant_auto_debug(event, auto, **extra):
    try:
        logger.info("[MUTANT_AUTO_DEBUG] %s %s", str(event or "state"), json.dumps(_debug_snapshot(auto, **extra), sort_keys=True))
    except Exception:
        logger.info("[MUTANT_AUTO_DEBUG] %s", str(event or "state"))


def ensure_mutant_auto_state(ntt):
    if not isinstance(ntt, dict):
        return default_mutant_auto_state()
    auto = ntt.get("auto")
    base = default_mutant_auto_state()
    if not isinstance(auto, dict):
        auto = {}
    for key, value in base.items():
        if key not in auto:
            auto[key] = value.copy() if isinstance(value, dict) else value
    auto["enabled"] = bool(auto.get("enabled", False))
    auto["barrier"] = _normalize_barrier_text(auto.get("barrier", "+0.12"))
    auto["budget"] = max(MIN_MUTANT_AUTO_STAKE, round(_safe_float(auto.get("budget", 10.0), 10.0), 2))
    selected_side = str(auto.get("selected_side") or "TOUCH").strip().upper()
    auto["selected_side"] = selected_side if selected_side in ("TOUCH", "NO_TOUCH") else "TOUCH"
    auto["martingale_enabled"] = bool(auto.get("martingale_enabled", False))
    auto["step50_enabled"] = bool(auto.get("step50_enabled", False))
    if auto["martingale_enabled"] and auto["step50_enabled"]:
        auto["step50_enabled"] = False
    auto["current_stake"] = max(0.0, round(_safe_float(auto.get("current_stake", 0.0), 0.0), 2))
    try:
        auto["progression_step"] = max(0, int(auto.get("progression_step", 0) or 0))
    except Exception:
        auto["progression_step"] = 0
    auto["active_stake"] = max(0.0, round(_safe_float(auto.get("active_stake", 0.0), 0.0), 2))
    auto["pending_contract_id"] = str(auto.get("pending_contract_id") or "").strip() or None
    auto["request_in_flight"] = bool(auto.get("request_in_flight", False))
    auto["request_started_at"] = max(0.0, _safe_float(auto.get("request_started_at", 0.0), 0.0))
    auto["execution_lock"] = bool(auto.get("execution_lock", False))
    try:
        auto["entry_cycle_id"] = max(0, int(auto.get("entry_cycle_id", 0) or 0))
    except Exception:
        auto["entry_cycle_id"] = 0
    auto["active_signal_id"] = str(auto.get("active_signal_id") or "").strip() or None
    auto["last_signal_id"] = str(auto.get("last_signal_id") or "").strip() or None
    auto["last_signal_started_at"] = max(0.0, _safe_float(auto.get("last_signal_started_at", 0.0), 0.0))
    auto["active_side"] = str(auto.get("active_side") or "").strip().upper() or None
    auto["active_symbol"] = str(auto.get("active_symbol") or "").strip().upper() or None
    try:
        active_step_index = auto.get("active_step_index")
        auto["active_step_index"] = None if active_step_index in (None, "") else max(0, int(active_step_index))
    except Exception:
        auto["active_step_index"] = None
    auto["active_next_loss_stake"] = max(0.0, round(_safe_float(auto.get("active_next_loss_stake", 0.0), 0.0), 2))
    auto["last_progress_contract_id"] = str(auto.get("last_progress_contract_id") or "").strip() or None
    auto["last_reason"] = str(auto.get("last_reason") or "Mutant AUTO is OFF.")
    auto["last_decision"] = str(auto.get("last_decision") or "OFF").strip().upper() or "OFF"
    auto["last_score"] = round(_safe_float(auto.get("last_score", 0.0), 0.0), 1)
    auto["last_touch_pct"] = round(_safe_float(auto.get("last_touch_pct", 0.0), 0.0), 1)
    auto["last_no_touch_pct"] = round(_safe_float(auto.get("last_no_touch_pct", 0.0), 0.0), 1)
    auto["last_started_at"] = max(0.0, _safe_float(auto.get("last_started_at", 0.0), 0.0))
    auto["trade_phase"] = _normalize_trade_phase(auto.get("trade_phase", MUTANT_AUTO_PHASE_IDLE))
    auto["active_plan"] = _normalize_active_plan(auto.get("active_plan"))
    auto["last_trade_result"] = str(auto.get("last_trade_result") or "").strip().upper() or None
    auto["last_trade_contract_id"] = str(auto.get("last_trade_contract_id") or "").strip() or None
    auto["consumed_contract_ids"] = _normalize_consumed_contract_ids(auto.get("consumed_contract_ids"))
    auto["pending_settlement"] = _normalize_pending_settlement(auto.get("pending_settlement"))
    ntt["auto"] = auto
    return auto


def mutant_auto_mode(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    if safe.get("martingale_enabled"):
        return "MARTINGALE"
    if safe.get("step50_enabled"):
        return "STEP50"
    return "BASE"


def mutant_auto_mode_label(auto):
    mode = mutant_auto_mode(auto)
    if mode == "MARTINGALE":
        return "MARTINGALE"
    if mode == "STEP50":
        return "50 CENTS MARTINGALE"
    return "BASE"


def mutant_auto_current_stake(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    mode = mutant_auto_mode(safe)
    if mode == "BASE":
        return round(safe.get("budget", MIN_MUTANT_AUTO_STAKE), 2)
    current = round(_safe_float(safe.get("current_stake", 0.0), 0.0), 2)
    if current >= MIN_MUTANT_AUTO_STAKE:
        return current
    return round(MIN_MUTANT_AUTO_STAKE, 2)


def _mutant_auto_ladder_for_mode(mode):
    safe_mode = str(mode or "BASE").strip().upper()
    if safe_mode == "MARTINGALE":
        return MARTINGALE_LADDER
    if safe_mode == "STEP50":
        return STEP50_LADDER
    return ()


def _mutant_auto_capped_ladder(mode, budget=None):
    ladder = _mutant_auto_ladder_for_mode(mode)
    if not ladder:
        return ()
    safe_limit = round(max(MIN_MUTANT_AUTO_STAKE, float(MAX_MUTANT_AUTO_LADDER_STAKE)), 2)
    capped = tuple(stake for stake in ladder if stake <= (safe_limit + 1e-9))
    return capped or (round(MIN_MUTANT_AUTO_STAKE, 2),)


def _project_mutant_auto_progression_stake(mode, budget, step_index):
    safe_mode = str(mode or "BASE").strip().upper()
    if safe_mode == "BASE":
        return 0.0
    ladder = _mutant_auto_capped_ladder(safe_mode, budget)
    if not ladder:
        return 0.0
    safe_step = max(0, int(step_index or 0))
    safe_step = min(safe_step, len(ladder) - 1)
    return round(float(ladder[safe_step]), 2)


def _mutant_auto_last_step_index(mode, budget):
    ladder = _mutant_auto_capped_ladder(mode, budget)
    if not ladder:
        return 0
    return max(0, len(ladder) - 1)


def mutant_auto_next_loss_stake(auto, *, step_index=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    mode = mutant_auto_mode(safe)
    budget = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(safe.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    if mode == "BASE":
        return 0.0
    current_step = max(0, int(step_index if step_index is not None else safe.get("progression_step", 0) or 0))
    return _project_mutant_auto_progression_stake(mode, budget, current_step + 1)


def build_mutant_auto_trade_plan(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    mode = mutant_auto_mode(safe)
    step_index = max(0, int(safe.get("progression_step", 0) or 0))
    current_stake = round(float(mutant_auto_current_stake(safe) or MIN_MUTANT_AUTO_STAKE), 2)
    next_loss_stake = round(float(mutant_auto_next_loss_stake(safe, step_index=step_index) or 0.0), 2)
    budget = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(safe.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    return {
        "mode": mode,
        "mode_label": mutant_auto_mode_label(safe),
        "step_index": step_index,
        "current_stake": current_stake,
        "next_loss_stake": next_loss_stake,
        "budget": budget,
        "stop_on_win": mode in ("MARTINGALE", "STEP50"),
        "stop_on_loss": mode == "BASE",
    }


def reset_mutant_auto_current_stake(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["progression_step"] = 0
    safe["active_step_index"] = None
    safe["active_next_loss_stake"] = 0.0
    safe["trade_phase"] = MUTANT_AUTO_PHASE_IDLE
    safe["active_plan"] = None
    mode = mutant_auto_mode(safe)
    if mode == "BASE":
        safe["current_stake"] = round(safe.get("budget", MIN_MUTANT_AUTO_STAKE), 2)
    else:
        safe["current_stake"] = round(MIN_MUTANT_AUTO_STAKE, 2)
    return safe["current_stake"]


def apply_mutant_auto_settings(
    ntt,
    *,
    barrier=None,
    budget=None,
    selected_side=None,
    martingale_enabled=None,
    step50_enabled=None,
):
    auto = ensure_mutant_auto_state(ntt)
    if barrier is not None:
        auto["barrier"] = _normalize_barrier_text(barrier, auto.get("barrier", "+0.12"))
    if budget is not None:
        auto["budget"] = max(MIN_MUTANT_AUTO_STAKE, round(_safe_float(budget, auto.get("budget", 10.0)), 2))
    if selected_side is not None:
        safe_side = str(selected_side or "TOUCH").strip().upper()
        auto["selected_side"] = safe_side if safe_side in ("TOUCH", "NO_TOUCH") else "TOUCH"
    if martingale_enabled is not None:
        auto["martingale_enabled"] = bool(martingale_enabled)
        if auto["martingale_enabled"]:
            auto["step50_enabled"] = False
    if step50_enabled is not None:
        auto["step50_enabled"] = bool(step50_enabled)
        if auto["step50_enabled"]:
            auto["martingale_enabled"] = False
    return auto


def arm_mutant_auto(
    ntt,
    *,
    barrier,
    budget,
    selected_side="TOUCH",
    martingale_enabled=False,
    step50_enabled=False,
    reason=None,
    started_at=0.0,
):
    auto = apply_mutant_auto_settings(
        ntt,
        barrier=barrier,
        budget=budget,
        selected_side=selected_side,
        martingale_enabled=martingale_enabled,
        step50_enabled=step50_enabled,
    )
    auto["enabled"] = True
    auto["pending_contract_id"] = None
    auto["request_in_flight"] = False
    auto["request_started_at"] = 0.0
    auto["execution_lock"] = False
    auto["entry_cycle_id"] = 0
    auto["active_signal_id"] = None
    auto["last_signal_id"] = None
    auto["last_signal_started_at"] = 0.0
    auto["active_side"] = None
    auto["active_symbol"] = None
    auto["active_stake"] = 0.0
    auto["active_step_index"] = None
    auto["active_next_loss_stake"] = 0.0
    auto["last_progress_contract_id"] = None
    reset_mutant_auto_current_stake(auto)
    auto["last_trade_result"] = None
    auto["last_trade_contract_id"] = None
    auto["pending_settlement"] = None
    auto["last_started_at"] = max(0.0, _safe_float(started_at, 0.0))
    auto["last_decision"] = "ARMED"
    auto["last_reason"] = str(reason or f"Mutant AUTO armed in {mutant_auto_mode_label(auto)} mode.")
    log_mutant_auto_debug("armed", auto, martingale_state_reset=True)
    return auto


def stop_mutant_auto(ntt, reason=None):
    auto = ensure_mutant_auto_state(ntt)
    auto["enabled"] = False
    auto["pending_contract_id"] = None
    auto["request_in_flight"] = False
    auto["request_started_at"] = 0.0
    auto["execution_lock"] = False
    auto["active_signal_id"] = None
    auto["last_signal_id"] = None
    auto["last_signal_started_at"] = 0.0
    auto["active_side"] = None
    auto["active_symbol"] = None
    auto["active_stake"] = 0.0
    auto["active_step_index"] = None
    auto["active_next_loss_stake"] = 0.0
    auto["last_progress_contract_id"] = None
    reset_mutant_auto_current_stake(auto)
    auto["pending_settlement"] = None
    auto["last_decision"] = "OFF"
    auto["last_reason"] = str(reason or "Mutant AUTO is OFF.")
    log_mutant_auto_debug("stopped", auto, martingale_state_reset=True)
    return auto


def mark_mutant_auto_trade_sent(auto, *, contract_id=None, side=None, symbol=None, stake=None, reason=None, started_at=0.0, signal_id=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["pending_contract_id"] = str(contract_id or "").strip() or None
    safe["request_in_flight"] = True
    safe["request_started_at"] = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    safe["last_started_at"] = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    safe["execution_lock"] = True
    safe["active_signal_id"] = str(signal_id or safe.get("active_signal_id") or "").strip() or None
    safe["last_signal_id"] = safe["active_signal_id"] or safe.get("last_signal_id")
    safe["last_signal_started_at"] = safe["request_started_at"]
    safe["active_side"] = str(side or "").strip().upper() or None
    safe["active_symbol"] = str(symbol or "").strip().upper() or None
    safe["active_stake"] = round(max(0.0, _safe_float(stake, 0.0)), 2)
    safe["current_stake"] = safe["active_stake"] or mutant_auto_current_stake(safe)
    safe["trade_phase"] = MUTANT_AUTO_PHASE_REQUESTING
    safe["pending_settlement"] = None
    safe["last_decision"] = "RUNNING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    log_mutant_auto_debug("trade_sent", safe)
    return safe


def begin_mutant_auto_request(auto, *, side=None, symbol=None, stake=None, reason=None, started_at=0.0, step_index=None, next_loss_stake=None, signal_id=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    started_ts = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    trade_plan = build_mutant_auto_trade_plan(safe)
    safe["active_plan"] = _build_active_plan(
        mode=trade_plan.get("mode") or mutant_auto_mode(safe),
        mode_label=trade_plan.get("mode_label") or mutant_auto_mode_label(safe),
        step_index=trade_plan.get("step_index") if step_index in (None, "") else step_index,
        current_stake=stake if stake is not None else trade_plan.get("current_stake"),
        next_loss_stake=trade_plan.get("next_loss_stake") if next_loss_stake is None else next_loss_stake,
        budget=trade_plan.get("budget") or safe.get("budget", MIN_MUTANT_AUTO_STAKE),
        stop_on_win=trade_plan.get("stop_on_win"),
        stop_on_loss=trade_plan.get("stop_on_loss"),
        selected_side=side or safe.get("selected_side"),
        symbol=symbol or safe.get("active_symbol"),
        barrier=safe.get("barrier"),
        request_started_at=started_ts,
    )
    safe["pending_contract_id"] = None
    safe["request_in_flight"] = True
    safe["request_started_at"] = started_ts
    safe["last_started_at"] = started_ts
    safe["execution_lock"] = True
    safe["active_signal_id"] = str(signal_id or safe.get("active_signal_id") or "").strip() or None
    safe["last_signal_id"] = safe["active_signal_id"] or safe.get("last_signal_id")
    safe["last_signal_started_at"] = started_ts
    safe["active_side"] = str(side or safe.get("active_side") or "").strip().upper() or None
    safe["active_symbol"] = str(symbol or safe.get("active_symbol") or "").strip().upper() or None
    safe["active_stake"] = round(max(0.0, _safe_float(stake, 0.0)), 2)
    try:
        safe["active_step_index"] = None if step_index in (None, "") else max(0, int(step_index))
    except Exception:
        safe["active_step_index"] = None
    safe["active_next_loss_stake"] = round(max(0.0, _safe_float(next_loss_stake, 0.0)), 2)
    if safe["active_stake"] > 0:
        safe["current_stake"] = safe["active_stake"]
    safe["trade_phase"] = MUTANT_AUTO_PHASE_REQUESTING
    safe["pending_settlement"] = None
    safe["last_decision"] = "SENDING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    log_mutant_auto_debug("request_begin", safe)
    return safe


def clear_mutant_auto_pending(auto, *, clear_plan=True):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["pending_contract_id"] = None
    safe["request_in_flight"] = False
    safe["request_started_at"] = 0.0
    safe["execution_lock"] = False
    safe["active_signal_id"] = None
    safe["active_side"] = None
    safe["active_symbol"] = None
    safe["active_stake"] = 0.0
    safe["active_step_index"] = None
    safe["active_next_loss_stake"] = 0.0
    safe["trade_phase"] = MUTANT_AUTO_PHASE_IDLE
    safe["pending_settlement"] = None
    if clear_plan:
        safe["active_plan"] = None
    return safe


def schedule_mutant_auto_settlement(
    auto,
    *,
    won,
    profit,
    side=None,
    contract_id=None,
    contract_meta=None,
    ready_at=0.0,
    reason=None,
):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["pending_contract_id"] = None
    safe["request_in_flight"] = False
    safe["request_started_at"] = 0.0
    safe["execution_lock"] = True
    safe["trade_phase"] = MUTANT_AUTO_PHASE_SETTLING
    safe["pending_settlement"] = _normalize_pending_settlement(
        {
            "ready_at": ready_at,
            "won": won,
            "profit": profit,
            "side": side,
            "contract_id": contract_id,
            "contract_meta": contract_meta,
            "reason": reason,
        }
    )
    safe["last_decision"] = "WAITING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    log_mutant_auto_debug("settlement_waiting", safe)
    return safe


def consume_mutant_auto_scheduled_settlement(ntt, *, now_ts=None):
    auto = ensure_mutant_auto_state(ntt)
    pending = _normalize_pending_settlement(auto.get("pending_settlement"))
    if not pending:
        return None
    current_ts = max(0.0, _safe_float(now_ts, 0.0))
    if current_ts < float(pending.get("ready_at", 0.0) or 0.0):
        return {"ready": False, "wait": True}
    auto["pending_settlement"] = None
    return progress_mutant_auto_after_result(
        ntt,
        won=bool(pending.get("won")),
        profit=_safe_float(pending.get("profit", 0.0), 0.0),
        side=str(pending.get("side") or "").upper(),
        contract_id=pending.get("contract_id"),
        contract_meta=pending.get("contract_meta") or {},
    )


def mutant_auto_has_consumed_contract(auto, contract_id):
    safe = ensure_mutant_auto_state({"auto": auto})
    cid = _normalize_contract_text(contract_id)
    if not cid:
        return False
    if cid == str(safe.get("last_progress_contract_id") or "").strip():
        return True
    return cid in set(_normalize_consumed_contract_ids(safe.get("consumed_contract_ids")))


def remember_mutant_auto_consumed_contract(auto, contract_id):
    safe = ensure_mutant_auto_state({"auto": auto})
    cid = _normalize_contract_text(contract_id)
    if not cid:
        return safe
    items = _normalize_consumed_contract_ids(safe.get("consumed_contract_ids"))
    if cid not in items:
        items.append(cid)
    safe["consumed_contract_ids"] = _normalize_consumed_contract_ids(items)
    safe["last_progress_contract_id"] = cid
    return safe


def evaluate_mutant_auto_early_result(
    auto,
    *,
    contract_id=None,
    tick_count=None,
    duration=None,
    duration_unit="t",
    open_profit=None,
    buy_price=None,
    sell_price=None,
):
    safe = ensure_mutant_auto_state({"auto": auto})
    mode = mutant_auto_mode(safe)
    if mode not in ("MARTINGALE", "STEP50"):
        return None

    cid = _normalize_contract_text(contract_id)
    if cid and mutant_auto_has_consumed_contract(safe, cid):
        return {"decided": False, "duplicate": True, "contract_id": cid}

    unit = str(duration_unit or "t").strip().lower()
    if unit != "t":
        return None

    try:
        total_ticks = max(1, int(float(duration or 0)))
    except Exception:
        total_ticks = 0
    if total_ticks <= 1:
        return None

    try:
        elapsed_ticks = max(0, int(float(tick_count or 0)))
    except Exception:
        elapsed_ticks = 0
    if elapsed_ticks <= 0:
        return None

    try:
        profit_value = float(open_profit)
    except Exception:
        profit_value = None
    if profit_value is None or profit_value != profit_value:
        return None
    buy_value = _safe_float(buy_price, 0.0)
    try:
        sell_value = float(sell_price)
    except Exception:
        sell_value = buy_value + profit_value
    final_check_tick = max(1, total_ticks - 1)
    early_win_tick = max(2, total_ticks - 2)

    if elapsed_ticks >= final_check_tick:
        if profit_value < 0:
            return {
                "decided": True,
                "won": False,
                "result": "LOSS",
                "profit": float(profit_value),
                "contract_id": cid,
                "tick_count": elapsed_ticks,
                "reason": f"Mutant AUTO marked the trade as LOSS at {elapsed_ticks}/{total_ticks} ticks because open profit was negative.",
            }
        if profit_value > 0:
            return {
                "decided": True,
                "won": True,
                "result": "WIN",
                "profit": float(profit_value),
                "contract_id": cid,
                "tick_count": elapsed_ticks,
                "reason": f"Mutant AUTO marked the trade as WIN at {elapsed_ticks}/{total_ticks} ticks because open profit was positive.",
            }

    if elapsed_ticks >= early_win_tick and profit_value > 0 and sell_value > buy_value:
        return {
            "decided": True,
            "won": True,
            "result": "WIN",
            "profit": float(profit_value),
            "contract_id": cid,
            "tick_count": elapsed_ticks,
            "reason": f"Mutant AUTO helper marked the trade as WIN early at {elapsed_ticks}/{total_ticks} ticks because the contract stayed profitable before the 4/5 check.",
        }

    return {"decided": False, "duplicate": False, "contract_id": cid}


def confirm_mutant_auto_trade(auto, *, contract_id=None, contract_meta=None, reason=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    plan = _resolve_active_plan(safe, contract_meta)
    safe_contract_id = str(contract_id or plan.get("contract_id") or "").strip() or None
    if safe_contract_id:
        plan["contract_id"] = safe_contract_id
        safe["last_trade_contract_id"] = safe_contract_id
    safe["active_plan"] = plan
    safe["pending_contract_id"] = safe_contract_id
    safe["request_in_flight"] = False
    safe["request_started_at"] = 0.0
    safe["execution_lock"] = True
    safe["active_side"] = str(plan.get("selected_side") or safe.get("selected_side") or "TOUCH").strip().upper() or None
    safe["active_symbol"] = str(plan.get("symbol") or safe.get("active_symbol") or "").strip().upper() or None
    safe["active_stake"] = round(max(0.0, _safe_float(plan.get("current_stake", 0.0), 0.0)), 2)
    safe["current_stake"] = safe["active_stake"] or mutant_auto_current_stake(safe)
    try:
        safe["active_step_index"] = max(0, int(plan.get("step_index", 0) or 0))
    except Exception:
        safe["active_step_index"] = None
    safe["active_next_loss_stake"] = round(max(0.0, _safe_float(plan.get("next_loss_stake", 0.0), 0.0)), 2)
    safe["trade_phase"] = MUTANT_AUTO_PHASE_LIVE
    safe["last_decision"] = "RUNNING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    log_mutant_auto_debug("buy_confirmed", safe)
    return safe


def mark_mutant_auto_unknown(auto, *, reason=None):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["request_in_flight"] = False
    safe["request_started_at"] = 0.0
    safe["execution_lock"] = True
    safe["trade_phase"] = MUTANT_AUTO_PHASE_UNKNOWN
    safe["last_decision"] = "WAITING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    log_mutant_auto_debug("unknown_state", safe)
    return safe


def progress_mutant_auto_after_result(ntt, *, won, profit, side=None, contract_id=None, contract_meta=None):
    auto = ensure_mutant_auto_state(ntt)
    safe_contract_id = _normalize_contract_text(contract_id)
    if safe_contract_id and mutant_auto_has_consumed_contract(auto, safe_contract_id):
        return {
            "continue": bool(auto.get("enabled")),
            "stopped": False,
            "next_stake": round(mutant_auto_current_stake(auto), 2),
            "duplicate": True,
        }
    if safe_contract_id:
        remember_mutant_auto_consumed_contract(auto, safe_contract_id)
    meta = contract_meta if isinstance(contract_meta, dict) else {}
    active_plan = _resolve_active_plan(auto, meta)
    mode = str(active_plan.get("mode") or mutant_auto_mode(auto)).strip().upper() or mutant_auto_mode(auto)
    active_stake = round(max(
        MIN_MUTANT_AUTO_STAKE,
        _safe_float(active_plan.get("current_stake", auto.get("current_stake", MIN_MUTANT_AUTO_STAKE)), MIN_MUTANT_AUTO_STAKE),
    ), 2)
    budget = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(auto.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    safe_side = str(side or active_plan.get("selected_side") or auto.get("active_side") or "TOUCH").strip().upper() or "TOUCH"
    auto["last_trade_result"] = "WIN" if won else "LOSS"
    auto["last_trade_contract_id"] = safe_contract_id or auto.get("last_trade_contract_id")
    auto["pending_contract_id"] = None
    auto["request_in_flight"] = False
    auto["request_started_at"] = 0.0
    auto["execution_lock"] = False
    auto["active_signal_id"] = None
    auto["active_side"] = None
    auto["active_symbol"] = None
    auto["active_stake"] = 0.0
    auto["active_step_index"] = None
    auto["active_next_loss_stake"] = 0.0
    auto["active_plan"] = None
    auto["trade_phase"] = MUTANT_AUTO_PHASE_IDLE

    if not bool(auto.get("enabled")):
        auto["last_decision"] = "OFF"
        auto["last_reason"] = str(auto.get("last_reason") or "Mutant AUTO is OFF.")
        log_mutant_auto_debug("settled_while_disabled", auto, martingale_state_reset=True)
        return {"continue": False, "stopped": True, "next_stake": 0.0, "duplicate": False}

    if mode == "BASE":
        auto["current_stake"] = budget
        auto["progression_step"] = 0
        if won:
            auto["last_decision"] = "CONTINUE"
            auto["last_reason"] = f"Base mode won on {safe_side}. AUTO keeps running at {budget:.2f}."
            log_mutant_auto_debug("settled_win_continue", auto)
            return {"continue": True, "stopped": False, "next_stake": budget, "duplicate": False}
        stop_mutant_auto(ntt, f"Base mode stopped after a loss on {safe_side}.")
        auto["last_trade_result"] = "LOSS"
        log_mutant_auto_debug("settled_loss_stop", auto)
        return {"continue": False, "stopped": True, "next_stake": 0.0, "duplicate": False}

    if won:
        stop_mutant_auto(ntt, f"{mutant_auto_mode_label(auto)} stopped after a win on {safe_side}.")
        auto["last_trade_result"] = "WIN"
        log_mutant_auto_debug("settled_win_stop", auto)
        return {"continue": False, "stopped": True, "next_stake": 0.0, "duplicate": False}

    try:
        active_step_index = max(0, int(active_plan.get("step_index", auto.get("progression_step", 0)) or 0))
    except Exception:
        active_step_index = max(0, int(auto.get("progression_step", 0) or 0))
    last_step = _mutant_auto_last_step_index(mode, budget)
    next_step = min(active_step_index + 1, last_step)
    # Always project from the current ladder/step. Stored metadata can survive
    # from an older frontend/backend cycle and must not override martingale.
    next_stake = round(max(0.0, _project_mutant_auto_progression_stake(mode, budget, next_step)), 2)
    if next_stake <= 0.0:
        next_stake = _project_mutant_auto_progression_stake(mode, budget, next_step)

    auto["enabled"] = True
    auto["progression_step"] = next_step
    auto["current_stake"] = next_stake
    auto["trade_phase"] = MUTANT_AUTO_PHASE_IDLE
    auto["last_decision"] = "REARMED"
    if next_step >= last_step:
        auto["last_reason"] = (
            f"{mutant_auto_mode_label(auto)} lost on {safe_side}. Repeating {next_stake:.2f} "
            f"as the top allowed stake within the {budget:.2f} budget."
        )
        log_mutant_auto_debug("loss_rearmed_repeat_top", auto, next_calculated_stake=next_stake)
    else:
        auto["last_reason"] = (
            f"{mutant_auto_mode_label(auto)} lost on {safe_side}. Next stake is {next_stake:.2f} "
            f"within the {budget:.2f} budget."
        )
        log_mutant_auto_debug("loss_rearmed", auto, next_calculated_stake=next_stake)
    return {"continue": True, "stopped": False, "next_stake": next_stake, "duplicate": False}


def serialize_mutant_auto(auto, *, active_count=0):
    safe = ensure_mutant_auto_state({"auto": auto})
    enabled = bool(safe.get("enabled"))
    pending_contract_id = str(safe.get("pending_contract_id") or "").strip()
    request_in_flight = bool(safe.get("request_in_flight", False))
    pending_settlement = _normalize_pending_settlement(safe.get("pending_settlement"))
    mode_label = mutant_auto_mode_label(safe)
    current_stake = mutant_auto_current_stake(safe)
    active_plan = _normalize_active_plan(safe.get("active_plan"))
    if not enabled:
        label = "OFF"
    elif active_count > 0 or pending_contract_id or request_in_flight or pending_settlement or bool(safe.get("execution_lock", False)):
        label = "RUNNING"
    else:
        label = "ARMED"
    return {
        "enabled": enabled,
        "label": label,
        "mode": mutant_auto_mode(safe),
        "mode_label": mode_label,
        "barrier": safe.get("barrier", "+0.12"),
        "budget": round(_safe_float(safe.get("budget", 10.0), 10.0), 2),
        "selected_side": safe.get("selected_side", "TOUCH"),
        "martingale_enabled": bool(safe.get("martingale_enabled", False)),
        "step50_enabled": bool(safe.get("step50_enabled", False)),
        "current_stake": round(current_stake, 2),
        "pending_contract_id": pending_contract_id or None,
        "request_in_flight": request_in_flight,
        "execution_lock": bool(safe.get("execution_lock", False)),
        "active_signal_id": safe.get("active_signal_id"),
        "last_signal_id": safe.get("last_signal_id"),
        "trade_phase": safe.get("trade_phase", MUTANT_AUTO_PHASE_IDLE),
        "pending_settlement_ready_at": float((pending_settlement or {}).get("ready_at") or 0.0),
        "active_side": safe.get("active_side"),
        "active_symbol": safe.get("active_symbol"),
        "next_loss_stake": round(_safe_float((active_plan or {}).get("next_loss_stake"), mutant_auto_next_loss_stake(safe)), 2),
        "last_trade_result": safe.get("last_trade_result"),
        "last_reason": str(safe.get("last_reason") or "Mutant AUTO is OFF."),
        "last_decision": str(safe.get("last_decision") or "OFF"),
        "last_score": round(_safe_float(safe.get("last_score", 0.0), 0.0), 1),
        "last_touch_pct": round(_safe_float(safe.get("last_touch_pct", 0.0), 0.0), 1),
        "last_no_touch_pct": round(_safe_float(safe.get("last_no_touch_pct", 0.0), 0.0), 1),
    }


def choose_mutant_auto_side(touch_pct, no_touch_pct):
    touch_value = round(_safe_float(touch_pct, 0.0), 1)
    no_touch_value = round(_safe_float(no_touch_pct, 0.0), 1)
    if no_touch_value > touch_value:
        return "NO_TOUCH", no_touch_value, touch_value, no_touch_value
    return "TOUCH", touch_value, touch_value, no_touch_value
