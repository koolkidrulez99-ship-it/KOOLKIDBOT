from collections import Counter, deque
import time


TESTTRIAL_DEFAULT_WINDOW = 20
TESTTRIAL_SHORT_WINDOW = 10
TESTTRIAL_RECENT_WINDOW = 5
TESTTRIAL_MICRO_WINDOW = 3
TESTTRIAL_SYMBOL_WARMUP_TICKS = 3
TESTTRIAL_LOSS_COOLDOWN_TICKS = 4
TESTTRIAL_WIN_COOLDOWN_TICKS = 2
TESTTRIAL_DEFAULT_MIN_TARGET = 0.15
TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE = 3.0
TESTTRIAL_DEFAULT_STAKE_MODE = "FIXED"
TESTTRIAL_DEFAULT_STRATEGY_MODE = "AUTO_COMBINED"
TESTTRIAL_DEFAULT_DURATION = 1
TESTTRIAL_DEFAULT_DURATION_UNIT = "t"

MIDDLE_DIGITS = {2, 3, 4, 5, 6, 7}
LOW_EDGE_DIGITS = {0, 1}
HIGH_EDGE_DIGITS = {8, 9}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def normalize_strategy_mode(value):
    mode = str(value or TESTTRIAL_DEFAULT_STRATEGY_MODE).upper().strip()
    if mode in ("OVER1", "OVER1_ONLY", "OVER 1"):
        return "OVER1_ONLY"
    if mode in ("UNDER8", "UNDER8_ONLY", "UNDER 8"):
        return "UNDER8_ONLY"
    return "AUTO_COMBINED"


def normalize_stake_mode(value):
    mode = str(value or TESTTRIAL_DEFAULT_STAKE_MODE).upper().strip()
    return "RATIO" if mode == "RATIO" else "FIXED"


def normalize_window_ticks(value):
    size = _safe_int(value, TESTTRIAL_DEFAULT_WINDOW)
    return max(10, min(50, size))


def normalize_min_target(value):
    target = _safe_float(value, TESTTRIAL_DEFAULT_MIN_TARGET)
    return round(max(0.0, min(25.0, target)), 2)


def normalize_max_total_stake(value):
    stake = _safe_float(value, TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE)
    return round(max(0.7, min(100.0, stake)), 2)


def _clean_digit(value):
    try:
        digit = int(value)
    except Exception:
        return None
    if 0 <= digit <= 9:
        return digit
    return None


def _contract_key_from_signal(contract_type, barrier):
    ctype = str(contract_type or "").upper().strip()
    try:
        b = int(barrier)
    except Exception:
        b = 0
    if ctype == "OVER" and b == 1:
        return "OVER 1"
    if ctype == "UNDER" and b == 8:
        return "UNDER 8"
    return f"{ctype} {b}".strip()


def create_testtrial_state():
    return {
        "enabled": False,
        "strategy_mode": TESTTRIAL_DEFAULT_STRATEGY_MODE,
        "stake_mode": TESTTRIAL_DEFAULT_STAKE_MODE,
        "window_ticks": TESTTRIAL_DEFAULT_WINDOW,
        "min_target": TESTTRIAL_DEFAULT_MIN_TARGET,
        "max_total_stake": TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE,
        "overplayed_filter_enabled": True,
        "strong_override_enabled": False,
        "digits": deque(maxlen=50),
        "current_symbol": "",
        "symbol_warmup_ticks_remaining": 0,
        "cooldown_ticks_remaining": 0,
        "cooldown_reason": "READY",
        "last_trade_result": None,
        "recent_results": deque(maxlen=6),
        "active_trade": None,
        "active_trade_open_contracts": 0,
        "both_cycle_profit": 0.0,
        "quotes": {
            "symbol": "",
            "updated_at": 0.0,
            "over1": None,
            "under8": None,
            "status": "Waiting for live quotes...",
        },
        "last_decision": {
            "action": "SKIP",
            "reason": "Waiting for live KOOLKID ticks...",
            "timestamp": 0.0,
        },
        "decision_log": deque(maxlen=80),
        "analysis": {},
        "reconnecting": False,
        "base_stake": 1.0,
    }


def apply_testtrial_settings(state, **updates):
    state["strategy_mode"] = normalize_strategy_mode(updates.get("strategy_mode", state.get("strategy_mode")))
    state["stake_mode"] = normalize_stake_mode(updates.get("stake_mode", state.get("stake_mode")))
    state["window_ticks"] = normalize_window_ticks(updates.get("window_ticks", state.get("window_ticks")))
    state["min_target"] = normalize_min_target(updates.get("min_target", state.get("min_target")))
    state["max_total_stake"] = normalize_max_total_stake(updates.get("max_total_stake", state.get("max_total_stake")))
    if "overplayed_filter_enabled" in updates:
        state["overplayed_filter_enabled"] = bool(updates.get("overplayed_filter_enabled"))
    if "strong_override_enabled" in updates:
        state["strong_override_enabled"] = bool(updates.get("strong_override_enabled"))
    return state


def set_enabled(state, enabled):
    state["enabled"] = bool(enabled)
    if not state["enabled"]:
        state["active_trade"] = None
        state["active_trade_open_contracts"] = 0
        state["both_cycle_profit"] = 0.0
        state["cooldown_reason"] = "DISABLED"
    elif not state.get("cooldown_ticks_remaining"):
        state["cooldown_reason"] = "READY"
    return bool(state["enabled"])


def record_tick(state, symbol, digit):
    clean_symbol = str(symbol or "").upper().strip()
    clean_digit = _clean_digit(digit)
    if clean_digit is None:
        return state

    previous_symbol = str(state.get("current_symbol") or "").upper().strip()
    if clean_symbol and clean_symbol != previous_symbol:
        state["current_symbol"] = clean_symbol
        state["digits"] = deque(maxlen=50)
        state["symbol_warmup_ticks_remaining"] = TESTTRIAL_SYMBOL_WARMUP_TICKS
        state["cooldown_reason"] = "SYMBOL CHANGE"
        state["quotes"] = {
            "symbol": clean_symbol,
            "updated_at": 0.0,
            "over1": None,
            "under8": None,
            "status": "Refreshing quotes after symbol change...",
        }
    elif clean_symbol:
        state["current_symbol"] = clean_symbol

    state["digits"].append(clean_digit)

    if state.get("symbol_warmup_ticks_remaining", 0) > 0:
        state["symbol_warmup_ticks_remaining"] = max(0, _safe_int(state.get("symbol_warmup_ticks_remaining"), 0) - 1)
        if state["symbol_warmup_ticks_remaining"] > 0:
            state["cooldown_reason"] = "SYMBOL WARMUP"
    if state.get("cooldown_ticks_remaining", 0) > 0:
        state["cooldown_ticks_remaining"] = max(0, _safe_int(state.get("cooldown_ticks_remaining"), 0) - 1)
        if state["cooldown_ticks_remaining"] > 0:
            state["cooldown_reason"] = f"COOLDOWN {state['cooldown_ticks_remaining']} tick(s)"
        elif state.get("enabled"):
            state["cooldown_reason"] = "READY"
    return state


def set_reconnecting(state, reconnecting):
    state["reconnecting"] = bool(reconnecting)
    return state


def set_quote_snapshot(state, *, symbol, over1_quote=None, under8_quote=None, status=None):
    state["quotes"] = {
        "symbol": str(symbol or state.get("current_symbol") or "").upper().strip(),
        "updated_at": time.time(),
        "over1": dict(over1_quote or {}) if over1_quote else None,
        "under8": dict(under8_quote or {}) if under8_quote else None,
        "status": str(status or "Quotes ready"),
    }
    return state


def _window(values, size):
    if size <= 0:
        return []
    return list(values[-size:])


def analyze_tick_window(digits, window_ticks=TESTTRIAL_DEFAULT_WINDOW):
    cleaned = [_clean_digit(d) for d in list(digits or [])]
    cleaned = [d for d in cleaned if d is not None]
    last20 = _window(cleaned, normalize_window_ticks(window_ticks))
    last10 = _window(cleaned, TESTTRIAL_SHORT_WINDOW)
    last5 = _window(cleaned, TESTTRIAL_RECENT_WINDOW)
    last3 = _window(cleaned, TESTTRIAL_MICRO_WINDOW)
    frequency = {str(d): 0 for d in range(10)}
    for digit, count in Counter(last20).items():
        frequency[str(digit)] = int(count)

    low_edge = sum(1 for d in last20 if d in LOW_EDGE_DIGITS)
    high_edge = sum(1 for d in last20 if d in HIGH_EDGE_DIGITS)
    middle_zone = sum(1 for d in last20 if d in MIDDLE_DIGITS)
    low_edge_10 = sum(1 for d in last10 if d in LOW_EDGE_DIGITS)
    high_edge_10 = sum(1 for d in last10 if d in HIGH_EDGE_DIGITS)
    middle_zone_10 = sum(1 for d in last10 if d in MIDDLE_DIGITS)

    overplayed_digits = sorted([digit for digit, count in Counter(last10).items() if int(count) >= 4])
    overplayed = bool(overplayed_digits)
    balanced_edges = low_edge_10 <= 2 and high_edge_10 <= 2 and abs(low_edge_10 - high_edge_10) <= 1
    calm_safe = bool(not overplayed and balanced_edges and middle_zone_10 >= 5)

    return {
        "last20_digits": list(last20),
        "last10_digits": list(last10),
        "last5_digits": list(last5),
        "last3_digits": list(last3),
        "low_edge": int(low_edge),
        "high_edge": int(high_edge),
        "middle_zone": int(middle_zone),
        "low_edge_10": int(low_edge_10),
        "high_edge_10": int(high_edge_10),
        "middle_zone_10": int(middle_zone_10),
        "frequency_map": frequency,
        "overplayed": overplayed,
        "overplayed_digits": overplayed_digits,
        "calm_safe_mode": calm_safe,
        "balanced_edges": balanced_edges,
        "sample_size": len(last20),
    }


def _has_recent_loss(recent_results, contract_key):
    window = list(recent_results or [])[-3:]
    for item in window:
        if str(item.get("contract") or "").upper() == str(contract_key or "").upper() and str(item.get("result") or "").upper() == "LOSS":
            return True
    return False


def calculate_scores(analysis, recent_results):
    last10 = list(analysis.get("last10_digits") or [])
    last5 = list(analysis.get("last5_digits") or [])
    last3 = list(analysis.get("last3_digits") or [])
    overplayed = bool(analysis.get("overplayed"))
    calm_safe = bool(analysis.get("calm_safe_mode"))

    over1_score = 0
    if sum(1 for d in last10 if d in LOW_EDGE_DIGITS) <= 1:
        over1_score += 40
    if not any(d in LOW_EDGE_DIGITS for d in last3):
        over1_score += 20
    if any(d in HIGH_EDGE_DIGITS for d in last5):
        over1_score += 10
    if not _has_recent_loss(recent_results, "OVER 1"):
        over1_score += 10
    if not overplayed:
        over1_score += 10
    if calm_safe:
        over1_score += 10

    under8_score = 0
    if sum(1 for d in last10 if d in HIGH_EDGE_DIGITS) <= 1:
        under8_score += 40
    if not any(d in HIGH_EDGE_DIGITS for d in last3):
        under8_score += 20
    if any(d in LOW_EDGE_DIGITS for d in last5):
        under8_score += 10
    if not _has_recent_loss(recent_results, "UNDER 8"):
        under8_score += 10
    if not overplayed:
        under8_score += 10
    if calm_safe:
        under8_score += 10

    both_score = 0
    if int(analysis.get("middle_zone_10", 0) or 0) >= 6:
        both_score += 40
    if (
        int(analysis.get("low_edge_10", 0) or 0) <= 2
        and int(analysis.get("high_edge_10", 0) or 0) <= 2
        and abs(int(analysis.get("low_edge_10", 0) or 0) - int(analysis.get("high_edge_10", 0) or 0)) <= 1
    ):
        both_score += 20
    if len(last3) == 3 and all(d in MIDDLE_DIGITS for d in last3):
        both_score += 20

    return {
        "over1": int(over1_score),
        "under8": int(under8_score),
        "both": int(both_score),
    }

def _quote_profit_rate(quote):
    if not isinstance(quote, dict):
        return None
    ask_price = _safe_float(quote.get("ask_price"), 0.0)
    payout = _safe_float(quote.get("payout"), 0.0)
    profit = _safe_float(quote.get("profit"), payout - ask_price)
    if ask_price <= 0.0:
        return None
    return max(0.0, profit / ask_price)


def _fixed_both_stakes(base_stake, max_total_stake):
    stake = max(0.35, round(_safe_float(base_stake, 1.0), 2))
    total = round(stake * 2.0, 2)
    if total > max_total_stake:
        half = round(max_total_stake / 2.0, 2)
        stake = max(0.35, half)
    return round(stake, 2), round(stake, 2)


def _ratio_both_stakes(base_stake, max_total_stake, over_rate, under_rate):
    total_budget = round(min(max_total_stake, max(0.70, _safe_float(base_stake, 1.0) * 2.0)), 2)
    safe_over = max(0.01, float(over_rate or 0.01))
    safe_under = max(0.01, float(under_rate or 0.01))
    ratio = (safe_under + 1.0) / (safe_over + 1.0)
    under_stake = round(total_budget / (1.0 + ratio), 2)
    over_stake = round(total_budget - under_stake, 2)
    over_stake = max(0.35, over_stake)
    under_stake = max(0.35, under_stake)
    total = over_stake + under_stake
    if total > max_total_stake:
        scale = max_total_stake / total
        over_stake = round(max(0.35, over_stake * scale), 2)
        under_stake = round(max(0.35, under_stake * scale), 2)
    return round(over_stake, 2), round(under_stake, 2)


def evaluate_payout_safety(quotes, *, base_stake, stake_mode, min_target, max_total_stake):
    over_quote = (quotes or {}).get("over1")
    under_quote = (quotes or {}).get("under8")
    symbol = str((quotes or {}).get("symbol") or "").upper().strip()

    if not over_quote or not under_quote:
        return {
            "ok": False,
            "status": "Quote unavailable",
            "reason": "Waiting for live Over 1 / Under 8 quotes before BOTH mode can be used.",
            "symbol": symbol,
            "stake_o": 0.0,
            "stake_u": 0.0,
            "net_low": None,
            "net_high": None,
            "net_mid": None,
            "min_target": round(float(min_target), 2),
            "max_total_stake": round(float(max_total_stake), 2),
        }

    over_rate = _quote_profit_rate(over_quote)
    under_rate = _quote_profit_rate(under_quote)
    if over_rate is None or under_rate is None:
        return {
            "ok": False,
            "status": "Quote incomplete",
            "reason": "Deriv quote data is incomplete, so BOTH mode safety cannot be confirmed yet.",
            "symbol": symbol,
            "stake_o": 0.0,
            "stake_u": 0.0,
            "net_low": None,
            "net_high": None,
            "net_mid": None,
            "min_target": round(float(min_target), 2),
            "max_total_stake": round(float(max_total_stake), 2),
        }

    if normalize_stake_mode(stake_mode) == "RATIO":
        stake_o, stake_u = _ratio_both_stakes(base_stake, max_total_stake, over_rate, under_rate)
    else:
        stake_o, stake_u = _fixed_both_stakes(base_stake, max_total_stake)

    total_stake = round(stake_o + stake_u, 2)
    if total_stake > max_total_stake:
        return {
            "ok": False,
            "status": "Stake cap exceeded",
            "reason": f"BOTH mode stake split would exceed the max total stake cap of ${max_total_stake:.2f}.",
            "symbol": symbol,
            "stake_o": stake_o,
            "stake_u": stake_u,
            "total_stake": total_stake,
            "net_low": None,
            "net_high": None,
            "net_mid": None,
            "min_target": round(float(min_target), 2),
            "max_total_stake": round(float(max_total_stake), 2),
        }

    profit_o = round(stake_o * over_rate, 2)
    profit_u = round(stake_u * under_rate, 2)
    net_low = round(profit_u - stake_o, 2)
    net_high = round(profit_o - stake_u, 2)
    net_mid = round(profit_o + profit_u, 2)
    safety_ok = bool(net_low >= min_target and net_high >= min_target and net_mid >= min_target)
    reason = (
        f"Safe BOTH mode: low {net_low:+.2f}, high {net_high:+.2f}, middle {net_mid:+.2f}."
        if safety_ok else
        f"BOTH mode blocked: low {net_low:+.2f}, high {net_high:+.2f}, middle {net_mid:+.2f} vs target {float(min_target):+.2f}."
    )

    return {
        "ok": safety_ok,
        "status": "PASS" if safety_ok else "FAIL",
        "reason": reason,
        "symbol": symbol,
        "stake_o": stake_o,
        "stake_u": stake_u,
        "total_stake": total_stake,
        "profit_o": profit_o,
        "profit_u": profit_u,
        "net_low": net_low,
        "net_high": net_high,
        "net_mid": net_mid,
        "min_target": round(float(min_target), 2),
        "max_total_stake": round(float(max_total_stake), 2),
        "over_rate": round(float(over_rate), 4),
        "under_rate": round(float(under_rate), 4),
    }


def choose_decision(state, analysis, scores, payout_safety):
    window_ticks = int(state.get("window_ticks", TESTTRIAL_DEFAULT_WINDOW) or TESTTRIAL_DEFAULT_WINDOW)
    current_symbol = str(state.get("current_symbol") or "").upper().strip()

    if not current_symbol:
        return {"action": "SKIP", "reason": "Waiting for market symbol before scoring testtrial.", "scores": scores}
    if int(analysis.get("sample_size", 0) or 0) < window_ticks:
        return {"action": "SKIP", "reason": f"Waiting for {window_ticks} ticks on {current_symbol} to warm up testtrial.", "scores": scores}
    if bool(state.get("reconnecting")):
        return {"action": "SKIP", "reason": "Skipping while the websocket is reconnecting.", "scores": scores}
    if int(state.get("symbol_warmup_ticks_remaining", 0) or 0) > 0:
        return {"action": "SKIP", "reason": f"Skipping the first ticks after symbol change ({int(state.get('symbol_warmup_ticks_remaining', 0) or 0)} left).", "scores": scores}
    if int(state.get("cooldown_ticks_remaining", 0) or 0) > 0:
        return {"action": "SKIP", "reason": f"Cooldown active for {int(state.get('cooldown_ticks_remaining', 0) or 0)} more tick(s) after the last {str(state.get('last_trade_result') or '').lower() or 'trade' }.", "scores": scores}
    if state.get("active_trade"):
        active = state.get("active_trade") or {}
        return {"action": "SKIP", "reason": f"Skipping because {active.get('action', 'a trade')} is still active on {active.get('symbol', current_symbol)}.", "scores": scores}
    if bool(state.get("overplayed_filter_enabled")) and bool(analysis.get("overplayed")) and not bool(state.get("strong_override_enabled")):
        digits_label = ", ".join(str(d) for d in list(analysis.get("overplayed_digits") or []))
        return {"action": "SKIP", "reason": f"Skipping because overplayed digits are making the market unstable ({digits_label}).", "scores": scores}

    mode = normalize_strategy_mode(state.get("strategy_mode"))
    over1_score = int(scores.get("over1", 0) or 0)
    under8_score = int(scores.get("under8", 0) or 0)
    both_score = int(scores.get("both", 0) or 0)

    if mode == "OVER1_ONLY":
        if over1_score >= 70:
            return {"action": "OVER 1", "reason": f"OVER 1 selected because score {over1_score} meets the 70 threshold and the low edge stayed quiet.", "scores": scores}
        return {"action": "SKIP", "reason": f"Skipping because OVER 1 score is only {over1_score}/100.", "scores": scores}

    if mode == "UNDER8_ONLY":
        if under8_score >= 70:
            return {"action": "UNDER 8", "reason": f"UNDER 8 selected because score {under8_score} meets the 70 threshold and the high edge stayed quiet.", "scores": scores}
        return {"action": "SKIP", "reason": f"Skipping because UNDER 8 score is only {under8_score}/100.", "scores": scores}

    if both_score >= 80 and bool((payout_safety or {}).get("ok")):
        return {"action": "BOTH", "reason": f"BOTH selected because middle digits dominated, both edges stayed balanced, and payout safety passed ({(payout_safety or {}).get('status')}).", "scores": scores}
    if over1_score >= 70 and over1_score > (under8_score + 10) and both_score < 75:
        return {"action": "OVER 1", "reason": f"OVER 1 selected because {over1_score} beat UNDER 8 by more than 10 points while BOTH stayed below the 75 cutoff.", "scores": scores}
    if under8_score >= 70 and under8_score > (over1_score + 10) and both_score < 75:
        return {"action": "UNDER 8", "reason": f"UNDER 8 selected because {under8_score} beat OVER 1 by more than 10 points while BOTH stayed below the 75 cutoff.", "scores": scores}

    reason_parts = [f"OVER 1 {over1_score}", f"UNDER 8 {under8_score}", f"BOTH {both_score}"]
    if payout_safety and not payout_safety.get("ok"):
        reason_parts.append(str(payout_safety.get("reason") or "BOTH payout safety failed"))
    return {"action": "SKIP", "reason": " / ".join(reason_parts), "scores": scores}


def update_analysis_and_decision(state):
    analysis = analyze_tick_window(state.get("digits") or [], state.get("window_ticks"))
    scores = calculate_scores(analysis, state.get("recent_results") or [])
    payout = evaluate_payout_safety(
        state.get("quotes") or {},
        base_stake=float(state.get("base_stake", 1.0) or 1.0),
        stake_mode=state.get("stake_mode"),
        min_target=float(state.get("min_target", TESTTRIAL_DEFAULT_MIN_TARGET) or TESTTRIAL_DEFAULT_MIN_TARGET),
        max_total_stake=float(state.get("max_total_stake", TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE) or TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE),
    )
    if scores.get("both", 0) >= 60 and bool(payout.get("ok")):
        scores["both"] = min(100, int(scores.get("both", 0) or 0) + 20)
    decision = choose_decision(state, analysis, scores, payout)
    timestamp = time.time()
    state["analysis"] = {"analysis": analysis, "scores": scores, "payout_safety": payout, "decision": decision, "updated_at": timestamp}
    state["last_decision"] = {"action": str(decision.get("action") or "SKIP"), "reason": str(decision.get("reason") or ""), "timestamp": timestamp}
    state.setdefault("decision_log", deque(maxlen=80)).append({"time": timestamp, "symbol": str(state.get("current_symbol") or ""), "action": str(decision.get("action") or "SKIP"), "reason": str(decision.get("reason") or ""), "scores": dict(scores or {})})
    return state["analysis"]

def build_signals_from_decision(state, *, base_stake):
    analysis = state.get("analysis") or {}
    decision = (analysis.get("decision") or {})
    payout = (analysis.get("payout_safety") or {})
    action = str(decision.get("action") or "SKIP").upper().strip()
    symbol = str(state.get("current_symbol") or "").upper().strip()
    if action == "SKIP" or not symbol:
        return None

    if action == "OVER 1":
        return {
            "mode": "TESTTRIAL_OVER1",
            "type": "OVER",
            "barrier": 1,
            "stake": round(max(0.35, _safe_float(base_stake, 1.0)), 2),
            "symbol": symbol,
            "duration": TESTTRIAL_DEFAULT_DURATION,
            "duration_unit": TESTTRIAL_DEFAULT_DURATION_UNIT,
        }

    if action == "UNDER 8":
        return {
            "mode": "TESTTRIAL_UNDER8",
            "type": "UNDER",
            "barrier": 8,
            "stake": round(max(0.35, _safe_float(base_stake, 1.0)), 2),
            "symbol": symbol,
            "duration": TESTTRIAL_DEFAULT_DURATION,
            "duration_unit": TESTTRIAL_DEFAULT_DURATION_UNIT,
        }

    if action == "BOTH" and payout.get("ok"):
        return [
            {
                "mode": "TESTTRIAL_BOTH",
                "type": "OVER",
                "barrier": 1,
                "stake": round(max(0.35, _safe_float(payout.get("stake_o"), 0.35)), 2),
                "symbol": symbol,
                "duration": TESTTRIAL_DEFAULT_DURATION,
                "duration_unit": TESTTRIAL_DEFAULT_DURATION_UNIT,
            },
            {
                "mode": "TESTTRIAL_BOTH",
                "type": "UNDER",
                "barrier": 8,
                "stake": round(max(0.35, _safe_float(payout.get("stake_u"), 0.35)), 2),
                "symbol": symbol,
                "duration": TESTTRIAL_DEFAULT_DURATION,
                "duration_unit": TESTTRIAL_DEFAULT_DURATION_UNIT,
            },
        ]
    return None


def mark_trade_started(state, signals):
    first = signals[0] if isinstance(signals, list) else signals
    action = "BOTH" if isinstance(signals, list) else _contract_key_from_signal(first.get("type"), first.get("barrier"))
    state["active_trade"] = {
        "symbol": str((first or {}).get("symbol") or state.get("current_symbol") or "").upper().strip(),
        "action": action,
        "started_at": time.time(),
    }
    state["active_trade_open_contracts"] = len(signals) if isinstance(signals, list) else 1
    state["both_cycle_profit"] = 0.0
    return state


def mark_trade_failed(state):
    state["active_trade"] = None
    state["active_trade_open_contracts"] = 0
    state["both_cycle_profit"] = 0.0
    return state


def record_trade_settlement(state, *, mode, contract_type, barrier, profit):
    mode_name = str(mode or "").upper().strip()
    active_contracts = max(0, _safe_int(state.get("active_trade_open_contracts"), 0))
    profit_value = round(_safe_float(profit, 0.0), 2)

    if mode_name == "TESTTRIAL_BOTH":
        state["both_cycle_profit"] = round(_safe_float(state.get("both_cycle_profit"), 0.0) + profit_value, 2)
        active_contracts = max(0, active_contracts - 1)
        state["active_trade_open_contracts"] = active_contracts
        if active_contracts > 0:
            return state
        result = "WIN" if _safe_float(state.get("both_cycle_profit"), 0.0) > 0 else "LOSS"
        state["recent_results"].append({"contract": "BOTH", "result": result, "profit": round(_safe_float(state.get("both_cycle_profit"), 0.0), 2)})
        state["last_trade_result"] = result
        state["cooldown_ticks_remaining"] = TESTTRIAL_WIN_COOLDOWN_TICKS if result == "WIN" else TESTTRIAL_LOSS_COOLDOWN_TICKS
        state["cooldown_reason"] = f"{result} cooldown"
        state["active_trade"] = None
        state["both_cycle_profit"] = 0.0
        return state

    contract_key = _contract_key_from_signal(contract_type, barrier)
    result = "WIN" if profit_value > 0 else "LOSS"
    state["recent_results"].append({"contract": contract_key, "result": result, "profit": profit_value})
    state["last_trade_result"] = result
    state["cooldown_ticks_remaining"] = TESTTRIAL_WIN_COOLDOWN_TICKS if result == "WIN" else TESTTRIAL_LOSS_COOLDOWN_TICKS
    state["cooldown_reason"] = f"{result} cooldown"
    state["active_trade"] = None
    state["active_trade_open_contracts"] = 0
    state["both_cycle_profit"] = 0.0
    return state


def build_ui_payload(state):
    analysis_bundle = state.get("analysis") or {}
    analysis = analysis_bundle.get("analysis") or analyze_tick_window(state.get("digits") or [], state.get("window_ticks"))
    scores = analysis_bundle.get("scores") or {"over1": 0, "under8": 0, "both": 0}
    payout = analysis_bundle.get("payout_safety") or evaluate_payout_safety(
        state.get("quotes") or {},
        base_stake=float(state.get("base_stake", 1.0) or 1.0),
        stake_mode=state.get("stake_mode"),
        min_target=float(state.get("min_target", TESTTRIAL_DEFAULT_MIN_TARGET) or TESTTRIAL_DEFAULT_MIN_TARGET),
        max_total_stake=float(state.get("max_total_stake", TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE) or TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE),
    )
    decision = analysis_bundle.get("decision") or {"action": "SKIP", "reason": "Waiting for testtrial analysis."}
    quotes = state.get("quotes") or {}
    recent_log = list(state.get("decision_log") or [])[-5:]

    cooldown_label = "READY"
    if bool(state.get("reconnecting")):
        cooldown_label = "WS reconnecting"
    elif int(state.get("symbol_warmup_ticks_remaining", 0) or 0) > 0:
        cooldown_label = f"Symbol warmup • {int(state.get('symbol_warmup_ticks_remaining', 0) or 0)} tick(s)"
    elif int(state.get("cooldown_ticks_remaining", 0) or 0) > 0:
        cooldown_label = f"{str(state.get('last_trade_result') or 'Trade')} cooldown • {int(state.get('cooldown_ticks_remaining', 0) or 0)} tick(s)"

    return {
        "enabled": bool(state.get("enabled")),
        "strategy_mode": normalize_strategy_mode(state.get("strategy_mode")),
        "stake_mode": normalize_stake_mode(state.get("stake_mode")),
        "window_ticks": int(state.get("window_ticks", TESTTRIAL_DEFAULT_WINDOW) or TESTTRIAL_DEFAULT_WINDOW),
        "min_target": round(float(state.get("min_target", TESTTRIAL_DEFAULT_MIN_TARGET) or TESTTRIAL_DEFAULT_MIN_TARGET), 2),
        "max_total_stake": round(float(state.get("max_total_stake", TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE) or TESTTRIAL_DEFAULT_MAX_TOTAL_STAKE), 2),
        "overplayed_filter_enabled": bool(state.get("overplayed_filter_enabled")),
        "current_symbol": str(state.get("current_symbol") or ""),
        "last20_digits": list(analysis.get("last20_digits") or []),
        "counts": {
            "low_edge": int(analysis.get("low_edge", 0) or 0),
            "high_edge": int(analysis.get("high_edge", 0) or 0),
            "middle_zone": int(analysis.get("middle_zone", 0) or 0),
            "low_edge_10": int(analysis.get("low_edge_10", 0) or 0),
            "high_edge_10": int(analysis.get("high_edge_10", 0) or 0),
            "middle_zone_10": int(analysis.get("middle_zone_10", 0) or 0),
        },
        "frequency_map": dict(analysis.get("frequency_map") or {}),
        "overplayed": bool(analysis.get("overplayed")),
        "overplayed_digits": list(analysis.get("overplayed_digits") or []),
        "confidence": {
            "over1": int(scores.get("over1", 0) or 0),
            "under8": int(scores.get("under8", 0) or 0),
            "both": int(scores.get("both", 0) or 0),
        },
        "recommended_action": str(decision.get("action") or "SKIP"),
        "reason_text": str(decision.get("reason") or ""),
        "payout_safety": {
            "ok": bool(payout.get("ok")),
            "status": str(payout.get("status") or "WAIT"),
            "reason": str(payout.get("reason") or ""),
            "net_low": payout.get("net_low"),
            "net_high": payout.get("net_high"),
            "net_mid": payout.get("net_mid"),
            "stake_o": payout.get("stake_o"),
            "stake_u": payout.get("stake_u"),
            "total_stake": payout.get("total_stake"),
        },
        "cooldown": {
            "ticks_remaining": int(state.get("cooldown_ticks_remaining", 0) or 0),
            "status": cooldown_label,
            "active_trade": dict(state.get("active_trade") or {}),
        },
        "quotes": {
            "symbol": str(quotes.get("symbol") or ""),
            "updated_at": float(quotes.get("updated_at", 0.0) or 0.0),
            "status": str(quotes.get("status") or "Waiting for live quotes..."),
            "over1": dict(quotes.get("over1") or {}),
            "under8": dict(quotes.get("under8") or {}),
        },
        "recent_decisions": [
            {"time": float(item.get("time", 0.0) or 0.0), "symbol": str(item.get("symbol") or ""), "action": str(item.get("action") or "SKIP"), "reason": str(item.get("reason") or ""), "scores": dict(item.get("scores") or {})}
            for item in recent_log
        ],
    }
