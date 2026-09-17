"""Shared MT5 Hub authentication and trusted workspace context."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SECRET_FILE = DATA_DIR / "mt5_hub_auth_secret"
WORKSPACE_RE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
_LOCK = threading.RLock()
_WORKSPACE: ContextVar[str | None] = ContextVar("mt5_hub_workspace", default=None)


def _secret() -> bytes:
    configured = os.getenv("MT5_HUB_AUTH_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    with _LOCK:
        if SECRET_FILE.is_file():
            return SECRET_FILE.read_bytes().strip()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(48).encode("ascii")
        tmp = SECRET_FILE.with_suffix(".tmp")
        tmp.write_bytes(value)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(SECRET_FILE)
        return value


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _valid_workspace(value: str) -> bool:
    return bool(value) and len(value) <= 80 and all(char in WORKSPACE_RE for char in value)


def issue_token(workspace_id: str, user_id: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    if not _valid_workspace(workspace_id):
        raise ValueError("Invalid workspace identifier.")
    payload = {"workspace_id": workspace_id, "user_id": user_id, "exp": int(time.time()) + ttl_seconds, "jti": uuid.uuid4().hex}
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_token(token: str) -> dict[str, Any] | None:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            return None
        payload = json.loads(_decode(encoded).decode("utf-8"))
        if not isinstance(payload, dict) or int(payload.get("exp") or 0) < time.time():
            return None
        if not _valid_workspace(str(payload.get("workspace_id") or "")):
            return None
        return payload
    except Exception:
        return None


def workspace_from_authorization(value: str | None) -> str | None:
    if not value or not value.startswith("Bearer "):
        return None
    payload = verify_token(value[7:].strip())
    return str(payload["workspace_id"]) if payload else None


def internal_workspace_signature(workspace_id: str) -> str:
    return _encode(hmac.new(_secret(), f"mt5-internal:{workspace_id}".encode("utf-8"), hashlib.sha256).digest())


def verify_internal_workspace(workspace_id: str, signature: str | None) -> bool:
    return _valid_workspace(workspace_id) and bool(signature) and hmac.compare_digest(internal_workspace_signature(workspace_id), signature)


def set_workspace(workspace_id: str):
    if not _valid_workspace(workspace_id):
        raise ValueError("Invalid workspace identifier.")
    return _WORKSPACE.set(workspace_id)


def reset_workspace(token) -> None:
    _WORKSPACE.reset(token)


def current_workspace() -> str:
    value = _WORKSPACE.get()
    if not value:
        raise RuntimeError("MT5 Hub workspace context is missing.")
    return value


def workspace_ids(users_file: Path) -> list[str]:
    try:
        data = json.loads(users_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [str(row.get("workspace_id")) for row in data.get("users", []) if _valid_workspace(str(row.get("workspace_id") or ""))]
