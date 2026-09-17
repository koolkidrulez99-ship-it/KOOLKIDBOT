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


def load_snapshot() -> dict[str, Any] | None:
    with _LOCK:
        state_file = _state_file()
        if not state_file.exists():
            return None
        try:
            value = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        return value if isinstance(value, dict) else None


def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        state_file = _state_file()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp.replace(state_file)
        return snapshot


def clear_snapshot() -> None:
    with _LOCK:
        try:
            _state_file().unlink(missing_ok=True)
        except OSError:
            pass
