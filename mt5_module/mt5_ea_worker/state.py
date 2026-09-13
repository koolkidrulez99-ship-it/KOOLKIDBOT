from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "worker_state.json"
_LOCK = threading.RLock()


def read_state() -> dict[str, Any]:
    with _LOCK:
        if not STATE_FILE.exists():
            return {"assignments": []}
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return deepcopy(data if isinstance(data, dict) else {"assignments": []})
        except Exception:
            return {"assignments": []}


def write_state(state: dict[str, Any]) -> None:
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp = STATE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temp.replace(STATE_FILE)
