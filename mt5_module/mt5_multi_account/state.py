import json, threading
from pathlib import Path

class State:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self):
        with self.lock:
            if not self.path.exists():
                return {"accounts": {}, "master": None, "slaves": [], "copy_map": {}}
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {"accounts": {}, "master": None, "slaves": [], "copy_map": {}}

    def save(self, value):
        with self.lock:
            # Passwords are never stored by callers.
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
            tmp.replace(self.path)
