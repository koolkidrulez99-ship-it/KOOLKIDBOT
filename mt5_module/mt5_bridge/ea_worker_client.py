from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("MT5_EA_WORKER_URL", "http://127.0.0.1:8001").rstrip("/")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_auth import current_workspace, internal_workspace_signature


def request(path: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 4.0):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    token = os.getenv("MT5_WORKER_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    workspace_id = current_workspace()
    headers.update({"X-MT5-Workspace": workspace_id, "X-MT5-Internal-Signature": internal_workspace_signature(workspace_id)})
    req = Request(f"{BASE_URL}{path}", data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        raise RuntimeError(detail or f"EA worker request failed ({exc.code}).") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("EA Worker Offline. Start KOOLKID with START_KOOLKID.bat.") from exc


def status() -> dict[str, Any]:
    try:
        health = request("/health", timeout=1.5)
        terminals = request("/terminals", timeout=2.5)
        return {"status": "online", "message": "EA worker is ready.", "endpoint": BASE_URL, "terminals": terminals, **health}
    except RuntimeError as exc:
        message = str(exc)
        status_value = "error" if "credentials" in message.lower() or "request failed" in message.lower() else "offline"
        return {"status": status_value, "message": message, "endpoint": BASE_URL, "terminals": []}
