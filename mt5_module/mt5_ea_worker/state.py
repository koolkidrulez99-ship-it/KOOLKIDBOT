from __future__ import annotations

import json
import threading
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT.parent))
from hub_auth import current_workspace
_LOCK = threading.RLock()


def _state_file() -> Path:
    return DATA_DIR / "workspaces" / current_workspace() / "worker_state.json"


def read_state() -> dict[str, Any]:
    with _LOCK:
        state_file = _state_file()
        if not state_file.exists():
            return {"assignments": []}
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return deepcopy(data if isinstance(data, dict) else {"assignments": []})
        except Exception:
            return {"assignments": []}


def write_state(state: dict[str, Any]) -> None:
    with _LOCK:
        state_file = _state_file()
        state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp.replace(state_file)
