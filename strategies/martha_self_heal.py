from __future__ import annotations

import time
from typing import Any, Dict, Optional


DEFAULT_MAX_FAILURES = 3
DEFAULT_EVENT_LIMIT = 80


def ensure_martha_health(state: Dict[str, Any]) -> Dict[str, Any]:
    health = state.get("martha_self_heal")
    if not isinstance(health, dict):
        health = {}
        state["martha_self_heal"] = health
    health.setdefault("status", "READY")
    health.setdefault("consecutive_failures", 0)
    health.setdefault("max_failures", DEFAULT_MAX_FAILURES)
    health.setdefault("safe_stopped", False)
    health.setdefault("last_issue", "")
    health.setdefault("last_action", "")
    health.setdefault("last_check_at", 0.0)
    health.setdefault("events", [])
    health.setdefault("cooldowns", {})
    return health


def record_martha_event(
    state: Dict[str, Any],
    event: str,
    *,
    issue: str = "",
    action: str = "",
    details: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    health = ensure_martha_health(state)
    at = float(now if now is not None else time.time())
    row = {
        "at": at,
        "event": str(event or "unknown"),
        "issue": str(issue or ""),
        "action": str(action or ""),
        "details": dict(details or {}),
    }
    events = health.setdefault("events", [])
    events.append(row)
    if len(events) > DEFAULT_EVENT_LIMIT:
        del events[:-DEFAULT_EVENT_LIMIT]
    health["last_check_at"] = at
    if issue:
        health["last_issue"] = str(issue)
    if action:
        health["last_action"] = str(action)
    return row


def record_martha_failure(
    state: Dict[str, Any],
    issue: str,
    *,
    action: str = "",
    details: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    health = ensure_martha_health(state)
    health["consecutive_failures"] = int(health.get("consecutive_failures") or 0) + 1
    maximum = max(1, int(health.get("max_failures") or DEFAULT_MAX_FAILURES))
    health["safe_stopped"] = health["consecutive_failures"] >= maximum
    health["status"] = "SAFE_STOPPED" if health["safe_stopped"] else "RECOVERING"
    record_martha_event(
        state,
        "failure",
        issue=issue,
        action=action,
        details={
            **dict(details or {}),
            "consecutive_failures": health["consecutive_failures"],
            "max_failures": maximum,
        },
        now=now,
    )
    return health


def record_martha_success(
    state: Dict[str, Any],
    action: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    health = ensure_martha_health(state)
    health["consecutive_failures"] = 0
    health["safe_stopped"] = False
    health["status"] = "HEALTHY"
    record_martha_event(state, "recovered", action=action, details=details, now=now)
    return health


def martha_cooldown_ready(
    state: Dict[str, Any], key: str, cooldown_seconds: float, *, now: Optional[float] = None
) -> bool:
    health = ensure_martha_health(state)
    at = float(now if now is not None else time.time())
    cooldowns = health.setdefault("cooldowns", {})
    last = float(cooldowns.get(str(key), 0.0) or 0.0)
    if last and (at - last) < max(0.0, float(cooldown_seconds or 0.0)):
        return False
    cooldowns[str(key)] = at
    if len(cooldowns) > 200:
        cutoff = at - 3600.0
        for old_key, old_at in list(cooldowns.items()):
            if float(old_at or 0.0) < cutoff:
                cooldowns.pop(old_key, None)
    return True


def martha_health_snapshot(state: Dict[str, Any]) -> Dict[str, Any]:
    health = ensure_martha_health(state)
    return {
        "status": health.get("status"),
        "consecutive_failures": int(health.get("consecutive_failures") or 0),
        "max_failures": int(health.get("max_failures") or DEFAULT_MAX_FAILURES),
        "safe_stopped": bool(health.get("safe_stopped")),
        "last_issue": health.get("last_issue") or "",
        "last_action": health.get("last_action") or "",
        "last_check_at": float(health.get("last_check_at") or 0.0),
        "events": list(health.get("events") or [])[-20:],
    }
