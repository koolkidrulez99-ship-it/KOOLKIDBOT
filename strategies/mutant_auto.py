MIN_MUTANT_AUTO_STAKE = 0.35
STEP50_INCREMENT = 0.50


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
        "active_side": None,
        "active_symbol": None,
        "active_stake": 0.0,
        "last_reason": "Mutant AUTO is OFF.",
        "last_decision": "OFF",
        "last_score": 0.0,
        "last_touch_pct": 0.0,
        "last_no_touch_pct": 0.0,
        "last_started_at": 0.0,
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
    auto["active_side"] = str(auto.get("active_side") or "").strip().upper() or None
    auto["active_symbol"] = str(auto.get("active_symbol") or "").strip().upper() or None
    auto["last_reason"] = str(auto.get("last_reason") or "Mutant AUTO is OFF.")
    auto["last_decision"] = str(auto.get("last_decision") or "OFF").strip().upper() or "OFF"
    auto["last_score"] = round(_safe_float(auto.get("last_score", 0.0), 0.0), 1)
    auto["last_touch_pct"] = round(_safe_float(auto.get("last_touch_pct", 0.0), 0.0), 1)
    auto["last_no_touch_pct"] = round(_safe_float(auto.get("last_no_touch_pct", 0.0), 0.0), 1)
    auto["last_started_at"] = max(0.0, _safe_float(auto.get("last_started_at", 0.0), 0.0))
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


def reset_mutant_auto_current_stake(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["progression_step"] = 0
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
    auto["active_side"] = None
    auto["active_symbol"] = None
    auto["active_stake"] = 0.0
    reset_mutant_auto_current_stake(auto)
    auto["last_started_at"] = max(0.0, _safe_float(started_at, 0.0))
    auto["last_decision"] = "ARMED"
    auto["last_reason"] = str(reason or f"Mutant AUTO armed in {mutant_auto_mode_label(auto)} mode.")
    return auto


def stop_mutant_auto(ntt, reason=None):
    auto = ensure_mutant_auto_state(ntt)
    auto["enabled"] = False
    auto["pending_contract_id"] = None
    auto["request_in_flight"] = False
    auto["request_started_at"] = 0.0
    auto["active_side"] = None
    auto["active_symbol"] = None
    auto["active_stake"] = 0.0
    reset_mutant_auto_current_stake(auto)
    auto["last_decision"] = "OFF"
    auto["last_reason"] = str(reason or "Mutant AUTO is OFF.")
    return auto


def mark_mutant_auto_trade_sent(auto, *, contract_id=None, side=None, symbol=None, stake=None, reason=None, started_at=0.0):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["pending_contract_id"] = str(contract_id or "").strip() or None
    safe["request_in_flight"] = True
    safe["request_started_at"] = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    safe["last_started_at"] = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    safe["active_side"] = str(side or "").strip().upper() or None
    safe["active_symbol"] = str(symbol or "").strip().upper() or None
    safe["active_stake"] = round(max(0.0, _safe_float(stake, 0.0)), 2)
    safe["current_stake"] = safe["active_stake"] or mutant_auto_current_stake(safe)
    safe["last_decision"] = "RUNNING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    return safe


def begin_mutant_auto_request(auto, *, side=None, symbol=None, stake=None, reason=None, started_at=0.0):
    safe = ensure_mutant_auto_state({"auto": auto})
    started_ts = max(0.0, _safe_float(started_at, safe.get("last_started_at", 0.0)))
    safe["pending_contract_id"] = None
    safe["request_in_flight"] = True
    safe["request_started_at"] = started_ts
    safe["last_started_at"] = started_ts
    safe["active_side"] = str(side or safe.get("active_side") or "").strip().upper() or None
    safe["active_symbol"] = str(symbol or safe.get("active_symbol") or "").strip().upper() or None
    safe["active_stake"] = round(max(0.0, _safe_float(stake, 0.0)), 2)
    if safe["active_stake"] > 0:
        safe["current_stake"] = safe["active_stake"]
    safe["last_decision"] = "SENDING"
    if reason is not None:
        safe["last_reason"] = str(reason)
    return safe


def clear_mutant_auto_pending(auto):
    safe = ensure_mutant_auto_state({"auto": auto})
    safe["pending_contract_id"] = None
    safe["request_in_flight"] = False
    safe["request_started_at"] = 0.0
    safe["active_side"] = None
    safe["active_symbol"] = None
    safe["active_stake"] = 0.0
    return safe


def progress_mutant_auto_after_result(ntt, *, won, profit, side=None):
    auto = ensure_mutant_auto_state(ntt)
    mode = mutant_auto_mode(auto)
    active_stake = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(auto.get("active_stake", auto.get("current_stake", MIN_MUTANT_AUTO_STAKE)), MIN_MUTANT_AUTO_STAKE)), 2)
    budget = round(max(MIN_MUTANT_AUTO_STAKE, _safe_float(auto.get("budget", MIN_MUTANT_AUTO_STAKE), MIN_MUTANT_AUTO_STAKE)), 2)
    safe_side = str(side or auto.get("active_side") or "TOUCH").strip().upper() or "TOUCH"
    clear_mutant_auto_pending(auto)

    if mode == "BASE":
        auto["current_stake"] = budget
        if won:
            auto["last_decision"] = "CONTINUE"
            auto["last_reason"] = f"Base mode won on {safe_side}. AUTO keeps running at {budget:.2f}."
            return {"continue": True, "stopped": False, "next_stake": budget}
        stop_mutant_auto(ntt, f"Base mode stopped after a loss on {safe_side}.")
        return {"continue": False, "stopped": True, "next_stake": 0.0}

    if won:
        stop_mutant_auto(ntt, f"{mutant_auto_mode_label(auto)} stopped after a win on {safe_side}.")
        return {"continue": False, "stopped": True, "next_stake": 0.0}

    current_step = max(0, int(auto.get("progression_step", 0) or 0))
    next_step = current_step + 1
    if mode == "MARTINGALE":
        next_stake = round(MIN_MUTANT_AUTO_STAKE * (2 ** next_step), 2)
    else:
        next_stake = round(MIN_MUTANT_AUTO_STAKE + (STEP50_INCREMENT * next_step), 2)

    if next_stake > (budget + 1e-9):
        stop_mutant_auto(
            ntt,
            f"{mutant_auto_mode_label(auto)} stopped because next stake {next_stake:.2f} would exceed the {budget:.2f} budget.",
        )
        return {"continue": False, "stopped": True, "next_stake": 0.0}

    auto["enabled"] = True
    auto["progression_step"] = next_step
    auto["current_stake"] = next_stake
    auto["last_decision"] = "REARMED"
    auto["last_reason"] = (
        f"{mutant_auto_mode_label(auto)} lost on {safe_side}. Next stake is {next_stake:.2f} "
        f"within the {budget:.2f} budget."
    )
    return {"continue": True, "stopped": False, "next_stake": next_stake}


def serialize_mutant_auto(auto, *, active_count=0):
    safe = ensure_mutant_auto_state({"auto": auto})
    enabled = bool(safe.get("enabled"))
    pending_contract_id = str(safe.get("pending_contract_id") or "").strip()
    request_in_flight = bool(safe.get("request_in_flight", False))
    mode_label = mutant_auto_mode_label(safe)
    current_stake = mutant_auto_current_stake(safe)
    if not enabled:
        label = "OFF"
    elif active_count > 0 or pending_contract_id or request_in_flight:
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
        "active_side": safe.get("active_side"),
        "active_symbol": safe.get("active_symbol"),
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
