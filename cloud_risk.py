from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CloudRiskDecision:
    passed: bool
    reason: str
    details: dict


DEFAULT_RISK_SETTINGS = {
    "max_digit9_last10": 2,
    "max_digit9_last20": 4,
    "min_seconds_between_99_streaks": 20,
    "max_digit9_last5": 2,
}


def _as_int(value, fallback):
    try:
        return int(float(value))
    except Exception:
        return int(fallback)


def _as_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def merge_risk_settings(settings: dict | None) -> dict:
    merged = dict(DEFAULT_RISK_SETTINGS)
    for key, value in (settings or {}).items():
        if key in merged and value not in (None, ""):
            merged[key] = value
    merged["max_digit9_last10"] = max(0, _as_int(merged.get("max_digit9_last10"), 2))
    merged["max_digit9_last20"] = max(0, _as_int(merged.get("max_digit9_last20"), 4))
    merged["max_digit9_last5"] = max(0, _as_int(merged.get("max_digit9_last5"), 2))
    merged["min_seconds_between_99_streaks"] = max(0.0, _as_float(merged.get("min_seconds_between_99_streaks"), 20))
    return merged


def evaluate_under9_backup(
    digits: Iterable[int],
    *,
    settings: dict | None = None,
    now_ts: float = 0.0,
    last_99_streak_ts: float = 0.0,
) -> CloudRiskDecision:
    cfg = merge_risk_settings(settings)
    history = [int(d) for d in list(digits or []) if int(d) >= 0 and int(d) <= 9]
    last5 = history[-5:]
    last10 = history[-10:]
    last20 = history[-20:]
    count5 = last5.count(9)
    count10 = last10.count(9)
    count20 = last20.count(9)
    seconds_since_streak = None
    if last_99_streak_ts and now_ts:
        seconds_since_streak = max(0.0, float(now_ts) - float(last_99_streak_ts))

    details = {
        "digit9_last5": count5,
        "digit9_last10": count10,
        "digit9_last20": count20,
        "seconds_since_last_99": seconds_since_streak,
    }

    if count5 > int(cfg["max_digit9_last5"]):
        return CloudRiskDecision(False, "Backup thinking skipped: digit 9 is too hot in the last 5 ticks.", details)
    if count10 > int(cfg["max_digit9_last10"]):
        return CloudRiskDecision(False, "Backup thinking skipped: digit 9 appeared too often in the last 10 ticks.", details)
    if count20 > int(cfg["max_digit9_last20"]):
        return CloudRiskDecision(False, "Backup thinking skipped: digit 9 appeared too often in the last 20 ticks.", details)
    if seconds_since_streak is not None and seconds_since_streak < float(cfg["min_seconds_between_99_streaks"]):
        return CloudRiskDecision(False, "Backup thinking skipped: another 9,9 streak happened too recently.", details)
    return CloudRiskDecision(True, "Backup thinking passed.", details)
