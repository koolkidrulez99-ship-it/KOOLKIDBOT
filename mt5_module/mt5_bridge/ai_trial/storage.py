from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "data" / "ai_trial_state.json"


def load_snapshot() -> dict[str, Any] | None:
    with _LOCK:
        if not STATE_FILE.exists():
            return None
        try:
            value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
        return value if isinstance(value, dict) else None


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
        return snapshot


def clear_snapshot() -> None:
    with _LOCK:
        try:
            STATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass
