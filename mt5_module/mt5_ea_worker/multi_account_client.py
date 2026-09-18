from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("MT5_MULTI_ACCOUNT_URL", "http://127.0.0.1:8002").rstrip("/")


def request(path: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: float = 30.0):
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = Request(
        f"{BASE_URL}{path}", data=body, method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        raise RuntimeError(detail or f"MT5 account worker request failed ({exc.code}).") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("MT5 multi-account worker is offline.") from exc


def accounts() -> dict[str, Any]:
    return request("/accounts", timeout=5)


def connect(profile: dict[str, Any], password: str) -> dict[str, Any]:
    login = int(profile["login"])
    return request("/accounts/connect", "POST", {
        "account_id": f"session-{login}", "nickname": profile.get("nickname") or f"MT5 #{login}",
        "login": login, "broker": profile.get("broker") or "MetaTrader 5",
        "server": profile.get("server") or "", "password": password,
        "mode": "real", "symbol_aliases": {},
    }, timeout=90)


def disconnect(login: int) -> None:
    request(f"/accounts/session-{int(login)}/disconnect", "POST", {}, timeout=10)


def remove(login: int) -> None:
    request(f"/accounts/session-{int(login)}", "DELETE", timeout=10)


def connected_by_login() -> dict[int, dict[str, Any]]:
    return {int(row.get("login") or 0): row for row in accounts().get("accounts", []) if row.get("connected")}


def worker_for_login(login: int | None = None) -> dict[str, Any]:
    connected = connected_by_login()
    if login is not None:
        worker = connected.get(int(login))
        if not worker:
            raise RuntimeError(f"MT5 account #{int(login)} is disconnected.")
        return worker
    if not connected:
        raise RuntimeError("No MT5 account session is connected.")
    return next(iter(connected.values()))


def account_request(login: int | None, path: str, timeout: float = 15.0):
    worker = worker_for_login(login)
    return request(f"/accounts/{worker['account_id']}{path}", timeout=timeout)
