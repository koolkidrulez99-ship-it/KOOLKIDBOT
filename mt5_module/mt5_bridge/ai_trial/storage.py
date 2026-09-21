from __future__ import annotations

import json
import threading
import sys
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))
from hub_auth import current_workspace


def _state_file() -> Path:
    return ROOT / "data" / "workspaces" / current_workspace() / "ai_trial_state.json"


def normalize_snapshot(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    def as_float(raw: Any, default: float) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def as_int(raw: Any, default: int) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    snapshot = dict(value)
    shift = snapshot.get("structure_shift")
    if not isinstance(shift, dict):
        shift = {}
    snapshot["structure_shift"] = {
        "confirmed": bool(shift.get("confirmed")),
        "index": shift.get("index"),
        "time": shift.get("time"),
    }
    retest = snapshot.get("retest")
    if not isinstance(retest, dict):
        retest = {}
    snapshot["retest"] = {
        "level": retest.get("level"),
        "touched": bool(retest.get("touched")),
        "same_candle_blocked": bool(retest.get("same_candle_blocked")),
    }
    factors = snapshot.get("confidence_factors")
    snapshot["confidence_factors"] = list(factors) if isinstance(factors, list) else []
    snapshot["confidence"] = as_float(snapshot.get("confidence"), 0.0)
    for key in ("last_confirmed_high", "last_confirmed_low", "trendline", "protected_structure", "proposed_trade", "last_historical_signal"):
        snapshot.setdefault(key, None)
    rules = snapshot.get("rules")
    if not isinstance(rules, dict):
        rules = {}
    snapshot["rules"] = {
        "completed_candles_only": bool(rules.get("completed_candles_only", True)),
        "swing_left": as_int(rules.get("swing_left"), 0),
        "swing_right": as_int(rules.get("swing_right"), 0),
        "same_candle_shift_retest": bool(rules.get("same_candle_shift_retest")),
        "required_sequence": list(rules.get("required_sequence") or []) if isinstance(rules.get("required_sequence"), list) else [],
        "take_profit_r": as_float(rules.get("take_profit_r"), 2.0),
    }
    return snapshot


def load_snapshot() -> dict[str, Any] | None:
    with _LOCK:
        state_file = _state_file()
        if not state_file.exists():
            return None
        try:
            value = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        return normalize_snapshot(value)


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        normalized = normalize_snapshot(snapshot)
        if normalized is None:
            raise ValueError("AI trial snapshot must be an object.")
        state_file = _state_file()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
        tmp.replace(state_file)
        return normalized


def clear_snapshot() -> None:
    with _LOCK:
        try:
            _state_file().unlink(missing_ok=True)
        except OSError:
            pass
