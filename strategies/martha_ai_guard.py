from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_MARTHA_THRESHOLD = 60


def _clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = fallback
    if number != number:
        number = fallback
    return max(low, min(high, number))


def normalize_martha_settings(settings: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = settings or {}
    return {
        "enabled": bool(raw.get("enabled")),
        "threshold": int(_clamp(raw.get("threshold"), 1, 95, DEFAULT_MARTHA_THRESHOLD)),
        "emergency_reconnect": bool(raw.get("emergency_reconnect")),
        "updated_at": float(raw.get("updated_at") or 0.0),
    }


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_")


def _safe_digit(value: Any, fallback: int = 5) -> int:
    try:
        digit = int(value)
    except Exception:
        digit = fallback
    return max(0, min(9, digit))


def _recent_digits(strategy: Any, size: int = 20) -> List[int]:
    raw = list(getattr(strategy, "tick_digits", []) or [])
    digits: List[int] = []
    for value in raw[-size:]:
        try:
            digit = int(value)
        except Exception:
            continue
        if 0 <= digit <= 9:
            digits.append(digit)
    return digits


def _digit_percentages(strategy: Any) -> Dict[int, float]:
    raw = getattr(strategy, "digit_percentages", {}) or {}
    out = {digit: 0.0 for digit in range(10)}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, Iterable):
        items = enumerate(raw)
    else:
        items = []
    for key, value in items:
        try:
            digit = int(key)
            pct = float(value)
        except Exception:
            continue
        if 0 <= digit <= 9:
            out[digit] = max(0.0, min(100.0, pct))
    return out


def _count_digit(digits: List[int], wanted: Any) -> int:
    target = _safe_digit(wanted)
    return sum(1 for digit in digits if digit == target)


def _session_adjust(now: Optional[datetime] = None) -> Dict[str, Any]:
    hour = (now or datetime.utcnow()).hour
    london = 7 <= hour < 16
    new_york = 12 <= hour < 21
    overlap = 12 <= hour < 16
    if overlap:
        return {"adjust": 12, "reason": "London/New York overlap is active"}
    if london:
        return {"adjust": 7, "reason": "London session is active"}
    if new_york:
        return {"adjust": 7, "reason": "New York session is active"}
    return {"adjust": -8, "reason": "Off-session conditions are weaker"}


def _digit_flow_adjust(digits: List[int]) -> Dict[str, Any]:
    recent = digits[-10:]
    if len(recent) < 5:
        return {"adjust": 0, "reason": "Limited live digit data"}

    unique = len(set(recent))
    max_repeat = max((_count_digit(recent, digit) for digit in set(recent)), default=0)
    adjust = 0
    reasons: List[str] = []

    if unique >= 6:
        adjust += 8
        reasons.append("Recent digits are balanced")
    elif unique <= 3:
        adjust -= 10
        reasons.append("Recent digits are clustered")
    else:
        reasons.append("Recent digits are mixed")

    if max_repeat >= 4:
        adjust -= 10
        reasons.append("One digit is overplayed in the last 10")

    return {"adjust": adjust, "reason": ", ".join(reasons[:2])}


def _setup_adjust(signal: Dict[str, Any], strategy: Any) -> Dict[str, Any]:
    contract_type = _normalize_text(signal.get("type") or signal.get("contract_type"))
    barrier = _safe_digit(signal.get("barrier"), 5)
    digits20 = _recent_digits(strategy, 20)
    digits10 = digits20[-10:]
    percentages = _digit_percentages(strategy)
    pct = float(percentages.get(barrier, 0.0))

    if len(digits10) < 5:
        return {"adjust": 0, "reason": "Waiting for more recent digits"}

    adjust = 0
    reasons: List[str] = []

    if contract_type in ("DIFFERS", "DIGITDIFF", "DIGITDIFFERS"):
        count20 = _count_digit(digits20, barrier)
        if count20 <= 1:
            adjust += 18
            reasons.append("DIFFERS barrier is quiet")
        elif count20 >= 4:
            adjust -= 24
            reasons.append("DIFFERS barrier is overplayed")
        else:
            adjust += 4
            reasons.append("DIFFERS barrier is acceptable")

        if pct <= 10.0:
            adjust += 10
            reasons.append("Barrier percentage is low")
        elif pct >= 16.0:
            adjust -= 14
            reasons.append("Barrier percentage is high")
    elif contract_type in ("MATCHES", "DIGITMATCH"):
        count20 = _count_digit(digits20, barrier)
        if count20 >= 3:
            adjust += 15
            reasons.append("MATCH barrier has repeated recently")
        elif count20 == 0:
            adjust -= 12
            reasons.append("MATCH barrier is too quiet")
        else:
            adjust += 2
            reasons.append("MATCH barrier has mild activity")
    elif contract_type in ("OVER", "DIGITOVER"):
        losers = sum(1 for digit in digits10 if digit <= barrier)
        adjust += round(((len(digits10) - losers) / len(digits10) - 0.55) * 55)
        reasons.append("OVER losing digits are checked")
    elif contract_type in ("UNDER", "DIGITUNDER"):
        losers = sum(1 for digit in digits10 if digit >= barrier)
        adjust += round(((len(digits10) - losers) / len(digits10) - 0.55) * 55)
        reasons.append("UNDER losing digits are checked")
    else:
        adjust += 2
        reasons.append("Generic KidGx setup check")

    return {"adjust": adjust, "reason": ", ".join(reasons[:2])}


def evaluate_martha_auto_signal(
    settings: Optional[Dict[str, Any]],
    profile: str,
    signal: Dict[str, Any],
    strategy: Any,
    *,
    symbol: Optional[str] = None,
    stake: Any = None,
    duration: Any = None,
    duration_unit: str = "t",
) -> Dict[str, Any]:
    normalized = normalize_martha_settings(settings)
    mode = _normalize_text(signal.get("mode"))
    action_type = _normalize_text(signal.get("type") or signal.get("contract_type"))
    action = {
        "profile": _normalize_text(profile),
        "source": "backend_auto_signal",
        "mode": mode,
        "type": action_type,
        "label": f"{_normalize_text(profile)} {mode or action_type}",
        "barrier": signal.get("barrier"),
        "symbol": symbol or signal.get("symbol") or "",
        "stake": stake,
        "duration": duration,
        "duration_unit": duration_unit or "t",
    }

    if not normalized["enabled"] or mode != "KIDGX":
        return {
            "active": False,
            "approved": True,
            "confidence": 100,
            "threshold": normalized["threshold"],
            "reason": "Martha AI auto gate is not active for this signal",
            "action": action,
        }

    digits = _recent_digits(strategy, 20)
    if len(digits[-5:]) < 5:
        return {
            "active": True,
            "approved": True,
            "confidence": normalized["threshold"],
            "threshold": normalized["threshold"],
            "reason": "Martha has limited live data, so KidGx is allowed safely",
            "action": action,
        }

    session = _session_adjust()
    flow = _digit_flow_adjust(digits)
    setup = _setup_adjust(signal, strategy)
    score = 50 + session["adjust"] + flow["adjust"] + setup["adjust"]
    confidence = int(round(_clamp(score, 5, 95, 50)))
    approved = confidence >= normalized["threshold"]
    reasons = [session["reason"], flow["reason"], setup["reason"]]

    return {
        "active": True,
        "approved": approved,
        "confidence": confidence,
        "threshold": normalized["threshold"],
        "reason": ", ".join([reason for reason in reasons if reason][:3]),
        "action": action,
    }
