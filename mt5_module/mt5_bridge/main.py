from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT.parent))
from hub_auth import current_workspace, issue_token, reset_workspace, set_workspace, workspace_from_authorization, workspace_ids

import engine
import ea_worker_client
import multi_account_client
import native_runtime
from native_strategies import NATIVE_PRESETS
import ai_auto_select
import mq5_compiler
import backtest_manager
import journal_manager
from store import bot_library_revision, default_risk, read_state, remove_profile, update_state, upsert_profile
from ai_trial import clear_snapshot as clear_ai_trial_snapshot, load_snapshot as load_ai_trial_snapshot, save_snapshot as save_ai_trial_snapshot, run_human_apostle_trial

app = FastAPI(title="KOOLKID Local MT5 Bridge", version="1.0.0")

EA_LIBRARY = ROOT / "data" / "ea_library"
EA_LIBRARY.mkdir(parents=True, exist_ok=True)
MAX_EA_FILE_BYTES = 25 * 1024 * 1024
MAX_MQ5_FILE_BYTES = 5 * 1024 * 1024
_stats_history_lock = threading.Lock()
_stats_history_cache: dict[str, dict[str, Any]] = {}
_AI_SCANNERS: dict[str, threading.Thread] = {}
_AI_SCANNER_STOPS: dict[str, threading.Event] = {}
_AI_EXECUTION_LOCKS: dict[str, threading.RLock] = {}
_AI_SCANNERS_LOCK = threading.RLock()
_SECRET_INPUT = re.compile(r"(?:password|passwd|token|secret|license|licence|api.?key)", re.IGNORECASE)
_LIBRARY_UPDATE_LOCKS: dict[str, threading.RLock] = {}
_LIBRARY_UPDATE_LOCKS_GUARD = threading.RLock()


def _library_update_lock(workspace_id: str) -> threading.RLock:
    with _LIBRARY_UPDATE_LOCKS_GUARD:
        return _LIBRARY_UPDATE_LOCKS.setdefault(workspace_id, threading.RLock())


def _safe_upload_name(name: str, extension: str) -> str:
    base = Path(name or "").name
    if not base.lower().endswith(extension):
        raise HTTPException(status_code=400, detail=f"Expected a {extension} file.")
    base = re.sub(r"[^A-Za-z0-9._() -]+", "_", base).strip(" .")
    if not base:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return base


async def _save_upload(file: UploadFile, dest: Path, extension: str) -> dict[str, Any]:
    filename = _safe_upload_name(file.filename or "", extension)
    data = await file.read(MAX_EA_FILE_BYTES + 1)
    if len(data) > MAX_EA_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{filename} exceeds the 25 MB upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail=f"{filename} is empty.")
    if extension == ".ex5" and not data.startswith(b"EX5"):
        raise HTTPException(status_code=400, detail=f"{filename} is not a valid compiled MT5 EX5 file.")
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / filename
    path.write_bytes(data)
    result = {
        "filename": filename,
        "original_filename": Path(file.filename or "").name,
        "stored_filename": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "stored_path": str(path.relative_to(ROOT)),
    }
    if extension == ".ex5":
        result["analysis"] = {
            "format": "MT5 EX5", "compiled": True, "file_verified": True,
            "strategy_visibility": "Observed runtime behavior only; compiled source logic is not readable.",
        }
    elif extension == ".set":
        result["analysis"] = _analyze_set_data(data)
    return result


def _analyze_set_data(data: bytes) -> dict[str, Any]:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in data[:64]:
        text = data.decode("utf-16", errors="ignore")
    else:
        text = data.decode("utf-8", errors="ignore")
    inputs = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith((";", "#")) or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()[:120]
        value = value.split("||", 1)[0].strip()[:200]
        if not name:
            continue
        inputs.append({"name": name, "value": "[redacted]" if _SECRET_INPUT.search(name) else value})
    return {"format": "MT5 SET", "input_count": len(inputs), "inputs": inputs[:100], "truncated": len(inputs) > 100}
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5055", "http://localhost:5055"],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Authorization"],
)


@app.exception_handler(Exception)
async def unhandled_api_error(_request: Request, _exc: Exception):
    # Returning through FastAPI's exception stack lets CORSMiddleware retain
    # the local-origin headers even when an unexpected API error occurs.
    return JSONResponse(status_code=500, content={"detail": "MT5 Bridge internal error."})

LEGACY_HUB_USERS_FILE = ROOT / "data" / "mt5_hub_users.json"
HUB_USERS_FILE = ROOT / "data" / "mt5_hub_users_runtime.json"
GLOBAL_TRIAL_FILE = ROOT / "data" / "mt5_global_trial.json"
GLOBAL_TRIAL_START = "2026-09-18T00:00:00+00:00"
GLOBAL_TRIAL_END = "2026-10-18T00:00:00+00:00"
PRESENCE_FILE = ROOT / "data" / "mt5_hub_presence.json"
_HUB_USERS_LOCK = threading.RLock()
_GLOBAL_TRIAL_LOCK = threading.RLock()
_PRESENCE_LOCK = threading.RLock()


def _load_hub_users() -> dict[str, Any]:
    source = HUB_USERS_FILE if HUB_USERS_FILE.exists() else LEGACY_HUB_USERS_FILE
    if not source.exists():
        return {"version": 1, "users": []}
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        if not (isinstance(data, dict) and isinstance(data.get("users"), list)):
            return {"version": 1, "users": []}
        if source == LEGACY_HUB_USERS_FILE and not HUB_USERS_FILE.exists():
            _save_hub_users(data)
        return data
    except Exception:
        return {"version": 1, "users": []}


def _save_hub_users(data: dict[str, Any]) -> None:
    HUB_USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = HUB_USERS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(HUB_USERS_FILE)


def _global_trial_schedule() -> dict[str, Any]:
    default = {
        "version": 1,
        "start_at": GLOBAL_TRIAL_START,
        "end_at": GLOBAL_TRIAL_END,
        "duration_days": 30,
    }
    with _GLOBAL_TRIAL_LOCK:
        if GLOBAL_TRIAL_FILE.is_file():
            try:
                data = json.loads(GLOBAL_TRIAL_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("start_at") and data.get("end_at"):
                    return data
            except Exception:
                pass
        GLOBAL_TRIAL_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = GLOBAL_TRIAL_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(default, indent=2), encoding="utf-8")
        tmp.replace(GLOBAL_TRIAL_FILE)
        return default


def _global_trial_status() -> dict[str, Any]:
    schedule = _global_trial_schedule()
    now = datetime.now(timezone.utc)
    start = datetime.fromisoformat(str(schedule["start_at"]))
    end = datetime.fromisoformat(str(schedule["end_at"]))
    remaining = max(0, int((end - now).total_seconds()))
    return {
        **schedule,
        "server_now": now.isoformat(),
        "active": start <= now < end,
        "expired": now >= end,
        "remaining_seconds": remaining,
    }


def _password_hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000).hex()


ADMIN_RESERVED_USERNAME = "koolkidrulez"
ADMIN_BOOTSTRAP_SALT_HEX = "fb00282af98a7291957d91cdfd700506"
ADMIN_BOOTSTRAP_HASH = "ba91bf52148aa5a1275225c53c681cbc373561c74bde4f3100e9895c08bf73b3"


def _valid_admin_bootstrap_password(password: str) -> bool:
    candidate = _password_hash(password, bytes.fromhex(ADMIN_BOOTSTRAP_SALT_HEX))
    return hmac.compare_digest(candidate, ADMIN_BOOTSTRAP_HASH)


class HubAuthPayload(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=256)


def _hub_access_tier(row: dict[str, Any]) -> str:
    if str(row.get("role") or "user") == "admin":
        return "lifetime"
    return "lifetime" if str(row.get("access_tier") or "tester").lower() == "lifetime" else "tester"


def _hub_identity(row: dict[str, Any]) -> dict[str, str]:
    return {
        "user_id": str(row["id"]),
        "username": str(row["username"]),
        "workspace_id": str(row["workspace_id"]),
        "role": str(row.get("role") or "user"),
        "access_tier": _hub_access_tier(row),
    }


def _hub_user_for_workspace(workspace_id: str) -> dict[str, Any] | None:
    with _HUB_USERS_LOCK:
        return next((dict(item) for item in _load_hub_users()["users"] if str(item.get("workspace_id")) == workspace_id), None)


def _hub_user_is_banned(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("banned") is True)


def _is_black_rock_bot(bot: dict[str, Any] | None) -> bool:
    if not bot:
        return False
    candidates = (
        bot.get("name"),
        bot.get("display_title"),
        bot.get("ea_filename"),
        bot.get("ea_original_filename"),
    )
    return any(re.sub(r"[^a-z0-9]+", "", str(value or "").lower()).removesuffix("ex5") == "blackrock" for value in candidates)


def _current_workspace_is_lifetime() -> bool:
    row = _hub_user_for_workspace(current_workspace())
    return bool(row and _hub_access_tier(row) == "lifetime" and not _hub_user_is_banned(row))


def _visible_bots_for_current_user(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if _current_workspace_is_lifetime():
        return rows
    return [
        row for row in rows
        if not bool(row.get("lifetime_only")) and not _is_black_rock_bot(row)
    ]


def _require_black_rock_lifetime_access(bot: dict[str, Any] | None) -> None:
    lifetime_only = bool(bot and bot.get("lifetime_only"))
    if (lifetime_only or _is_black_rock_bot(bot)) and not _current_workspace_is_lifetime():
        raise HTTPException(status_code=403, detail="BLACK ROCK is available to Lifetime users only.")


def _presence_data() -> dict[str, Any]:
    try:
        data = json.loads(PRESENCE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _touch_presence(workspace_id: str) -> None:
    with _PRESENCE_LOCK:
        data = _presence_data()
        data[workspace_id] = datetime.now(timezone.utc).isoformat()
        PRESENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = PRESENCE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(PRESENCE_FILE)


def _require_admin(request: Request) -> dict[str, Any]:
    workspace_id = workspace_from_authorization(request.headers.get("Authorization"))
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Admin sign-in required.")
    row = _hub_user_for_workspace(workspace_id)
    if not row or str(row.get("role") or "user") != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return row


@app.middleware("http")
async def require_mt5_workspace(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path == "/health":
        return await call_next(request)
    if not path.startswith("/api/mt5/") or path.startswith("/api/mt5/hub/auth/"):
        return await call_next(request)
    workspace_id = workspace_from_authorization(request.headers.get("Authorization"))
    if not workspace_id:
        return JSONResponse(status_code=401, content={"detail": "Sign in to your MT5 Hub workspace."})
    user = _hub_user_for_workspace(workspace_id)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "MT5 Hub workspace no longer exists."})
    if _hub_user_is_banned(user):
        return JSONResponse(status_code=403, content={"detail": "Your MT5 Hub account has been banned."})
    context_token = set_workspace(workspace_id)
    try:
        return await call_next(request)
    finally:
        reset_workspace(context_token)


class AccountPayload(BaseModel):
    login: int
    password: str | None = None
    server: str | None = None
    nickname: str | None = None
    broker: str | None = None
    access_mode: str | None = None
    account_type: str | None = None
    leverage: int | None = None
    balance: float | None = None


class TradePayload(BaseModel):
    account_login: int
    symbol: str = Field(min_length=1, max_length=64)
    type: str
    volume: float = Field(gt=0)
    sl: float | None = None
    tp: float | None = None
    source: str | None = None
    confirm_live: bool = False


AiTimeframe = Literal["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


class AiTrialScanPayload(BaseModel):
    account_login: int
    symbol: str = Field(min_length=1, max_length=64)
    execution_timeframe: AiTimeframe = "M15"
    bias_timeframe: AiTimeframe = "H4"


class AiTrialExecutePayload(BaseModel):
    account_login: int
    symbol: str = Field(min_length=1, max_length=64)
    volume: float = Field(gt=0)
    confirm_live: bool = False


class AiAutoConfigPayload(BaseModel):
    enabled: bool
    account_login: int | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    volume: float | None = Field(default=None, gt=0)
    scan_seconds: int = Field(default=30, ge=15, le=300)
    execution_timeframe: AiTimeframe = "M15"
    bias_timeframe: AiTimeframe = "H4"
    confirm_live: bool = False


class AiAutoSelectScanPayload(BaseModel):
    account_login: int
    symbol: str = Field(min_length=1, max_length=64)
    enabled_bot_ids: list[int] = Field(default_factory=list)


class AiAutoSelectConfigPayload(BaseModel):
    enabled: bool
    account_login: int | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    enabled_bot_ids: list[int] = Field(default_factory=list)
    mode: str = "analysis"
    scan_seconds: int = Field(default=30, ge=15, le=300)
    confirm_live: bool = False


class AiAutoSelectExecutePayload(BaseModel):
    confirm_live: bool = False


@app.post("/api/mt5/hub/auth/signup")
def hub_signup(payload: HubAuthPayload):
    username = payload.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]+", username):
        raise HTTPException(status_code=400, detail="Use letters, numbers, dots, hyphens, or underscores for the username.")

    is_reserved_admin = username == ADMIN_RESERVED_USERNAME
    with _HUB_USERS_LOCK:
        users = _load_hub_users()

        # Usernames are globally unique, case-insensitively.
        if any(str(row.get("username", "")).strip().lower() == username for row in users["users"]):
            raise HTTPException(status_code=409, detail="Username already taken.")

        # The reserved admin username can never become a normal MT5 Hub user.
        # A wrong password is deliberately reported as "taken" so outsiders
        # cannot use signup to discover or claim the admin bootstrap account.
        if is_reserved_admin and not _valid_admin_bootstrap_password(payload.password):
            raise HTTPException(status_code=409, detail="Username already taken.")

        salt = os.urandom(16)
        row = {
            "id": uuid.uuid4().hex,
            "workspace_id": (
                f"admin_{uuid.uuid4().hex}"
                if is_reserved_admin
                else f"ws_{uuid.uuid4().hex}"
            ),
            "username": username,
            "role": "admin" if is_reserved_admin else "user",
            "access_tier": "lifetime" if is_reserved_admin else "tester",
            "password_salt": salt.hex(),
            "password_hash": _password_hash(payload.password, salt),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        users["users"].append(row)
        _save_hub_users(users)

    identity = _hub_identity(row)
    return {
        **identity,
        "token": issue_token(identity["workspace_id"], identity["user_id"]),
        "trial": _global_trial_status(),
    }


@app.get("/api/mt5/hub/auth/trial")
def hub_trial_status():
    return _global_trial_status()


@app.post("/api/mt5/hub/auth/login")
def hub_login(payload: HubAuthPayload):
    username = payload.username.strip().lower()
    with _HUB_USERS_LOCK:
        users = _load_hub_users()
        row = next(
            (
                item
                for item in users["users"]
                if str(item.get("username", "")).strip().lower() == username
            ),
            None,
        )
        if not row:
            raise HTTPException(status_code=401, detail="Invalid MT5 Hub login.")

        try:
            valid = hmac.compare_digest(
                str(row.get("password_hash", "")),
                _password_hash(
                    payload.password,
                    bytes.fromhex(str(row.get("password_salt", ""))),
                ),
            )
        except ValueError:
            valid = False

        if not valid:
            raise HTTPException(status_code=401, detail="Invalid MT5 Hub login.")
        if _hub_user_is_banned(row):
            raise HTTPException(status_code=403, detail="Your MT5 Hub account has been banned.")

        # Migration path for a reserved username that may have been created as
        # a normal Hub user before admin-role support existed on the server.
        if (
            username == ADMIN_RESERVED_USERNAME
            and str(row.get("role") or "user") != "admin"
            and _valid_admin_bootstrap_password(payload.password)
        ):
            row["role"] = "admin"
            row["workspace_id"] = f"admin_{uuid.uuid4().hex}"
            row["promoted_to_admin_at"] = datetime.now(timezone.utc).isoformat()
            _save_hub_users(users)

        identity = _hub_identity(row)

    return {
        **identity,
        "token": issue_token(identity["workspace_id"], identity["user_id"]),
        "trial": _global_trial_status(),
    }


@app.get("/api/mt5/hub/auth/me")
def hub_me(request: Request):
    workspace_id = workspace_from_authorization(request.headers.get("Authorization"))
    if not workspace_id:
        raise HTTPException(status_code=401, detail="Sign in to your MT5 Hub workspace.")
    with _HUB_USERS_LOCK:
        row = next((item for item in _load_hub_users()["users"] if item.get("workspace_id") == workspace_id), None)
    if not row:
        raise HTTPException(status_code=401, detail="MT5 Hub workspace no longer exists.")
    if _hub_user_is_banned(row):
        raise HTTPException(status_code=403, detail="Your MT5 Hub account has been banned.")
    return {**_hub_identity(row), "trial": _global_trial_status()}


@app.post("/api/mt5/hub/presence")
def hub_presence():
    workspace_id = current_workspace()
    _touch_presence(workspace_id)
    return {"ok": True, "seen_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/mt5/backtests")
def list_backtests():
    return backtest_manager.list_for_workspace(current_workspace())


@app.get("/api/mt5/backtests/{job_id}/report")
def backtest_report(job_id: str):
    workspace_id = current_workspace()
    job = backtest_manager.job_for_workspace(workspace_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backtest was not found.")
    report = backtest_manager.report_for_workspace(workspace_id, job_id)
    if not report:
        raise HTTPException(status_code=404, detail="This backtest did not produce an MT5 HTML report.")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(str(job.get("bot_filename") or "backtest")).stem) or "backtest"
    return FileResponse(
        report,
        media_type="text/html",
        filename=f"{stem}_backtest_report{report.suffix.lower() or '.html'}",
    )


@app.get("/api/mt5/backtests/{job_id}/data")
def backtest_data(job_id: str):
    job = backtest_manager.job_for_workspace(current_workspace(), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backtest was not found.")
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(str(job.get("bot_filename") or "backtest")).stem) or "backtest"
    return JSONResponse(
        content=job,
        headers={"Content-Disposition": f'attachment; filename="{stem}_backtest_data.json"'},
    )


@app.delete("/api/mt5/backtests/{job_id}")
def dismiss_backtest(job_id: str):
    try:
        return backtest_manager.dismiss_for_workspace(current_workspace(), job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Backtest was not found.")
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/mt5/backtests")
async def create_backtest(
    bot_file: UploadFile = File(...),
    preset_file: UploadFile | None = File(default=None),
    account_login: int = Form(...),
    symbol: str = Form(...),
    timeframe: str = Form("M15"),
    date_from: str = Form(...),
    date_to: str = Form(...),
    deposit: float = Form(10000),
    leverage: int = Form(100),
    model: int = Form(4),
    research_opt_in: bool = Form(False),
):
    workspace_id = current_workspace()
    user = _hub_user_for_workspace(workspace_id)
    if not user:
        raise HTTPException(status_code=401, detail="MT5 Hub user was not found.")
    if timeframe.upper() not in {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}:
        raise HTTPException(status_code=400, detail="Unsupported backtest timeframe.")
    if model not in {0, 1, 2, 4}:
        raise HTTPException(status_code=400, detail="Unsupported MT5 tester model.")
    try:
        start, end = datetime.fromisoformat(date_from), datetime.fromisoformat(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Use valid YYYY-MM-DD backtest dates.") from exc
    if end <= start:
        raise HTTPException(status_code=400, detail="Backtest end date must be after the start date.")
    bot_data = await bot_file.read(MAX_EA_FILE_BYTES + 1)
    preset_data = await preset_file.read(MAX_MQ5_FILE_BYTES + 1) if preset_file else None
    try:
        return backtest_manager.create_job(
            workspace_id, str(user.get("username") or "user"), account_login,
            bot_file.filename or "bot.ex5", bot_data,
            preset_file.filename if preset_file else None, preset_data,
            symbol, timeframe, date_from, date_to, deposit, leverage, model, research_opt_in,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _admin_online_snapshot() -> tuple[dict[str, str], set[str]]:
    presence = _presence_data()
    now = datetime.now(timezone.utc)
    online: set[str] = set()
    for workspace_id, seen in presence.items():
        try:
            if (now - datetime.fromisoformat(str(seen))).total_seconds() <= 120:
                online.add(str(workspace_id))
        except ValueError:
            continue
    return presence, online


@app.get("/api/mt5/admin/overview")
def admin_overview(request: Request):
    _require_admin(request)
    users = _load_hub_users()["users"]
    _, online = _admin_online_snapshot()
    jobs = backtest_manager.all_jobs()
    research = backtest_manager.all_research()
    active_states = {"queued", "preparing", "compiling", "testing", "analyzing"}
    return {
        "total_users": len([row for row in users if str(row.get("role") or "user") == "user"]),
        "online_users": len([row for row in users if row.get("workspace_id") in online and str(row.get("role") or "user") == "user" and not _hub_user_is_banned(row)]),
        "active_backtests": len([row for row in jobs if row.get("status") in active_states]),
        "completed_backtests": len([row for row in jobs if row.get("status") == "complete"]),
        "pending_research": len([row for row in research if row.get("status") == "pending"]),
        "approved_candidates": len([row for row in research if row.get("status") == "approved_candidate"]),
    }


@app.get("/api/mt5/admin/users")
def admin_users(request: Request):
    _require_admin(request)
    presence, online = _admin_online_snapshot()
    jobs = backtest_manager.all_jobs()
    rows = []
    for user in _load_hub_users()["users"]:
        workspace_id = str(user.get("workspace_id") or "")
        rows.append({
            "username": user.get("username"),
            "role": user.get("role") or "user",
            "access_tier": _hub_access_tier(user),
            "banned": _hub_user_is_banned(user),
            "banned_at": user.get("banned_at"),
            "banned_by": user.get("banned_by"),
            "joined_at": user.get("created_at"),
            "last_seen": presence.get(workspace_id),
            "online": workspace_id in online and not _hub_user_is_banned(user),
            "backtests": len([job for job in jobs if job.get("workspace_id") == workspace_id]),
        })
    return rows


@app.put("/api/mt5/admin/users/{username}/access")
def admin_user_access(username: str, request: Request, payload: dict[str, Any] = Body(...)):
    admin = _require_admin(request)
    target = username.strip().lower()
    requested = str(payload.get("access_tier") or "").strip().lower()
    if requested not in {"tester", "lifetime"}:
        raise HTTPException(status_code=422, detail="Access tier must be tester or lifetime.")
    with _HUB_USERS_LOCK:
        users = _load_hub_users()
        row = next(
            (
                item for item in users["users"]
                if str(item.get("username") or "").strip().lower() == target
            ),
            None,
        )
        if not row:
            raise HTTPException(status_code=404, detail="MT5 Hub user was not found.")
        if str(row.get("role") or "user") == "admin":
            raise HTTPException(status_code=409, detail="Admin access cannot be changed to a user tier.")
        row["access_tier"] = requested
        row["access_updated_at"] = datetime.now(timezone.utc).isoformat()
        row["access_updated_by"] = str(admin.get("username") or ADMIN_RESERVED_USERNAME)
        _save_hub_users(users)
        return {
            "username": row.get("username"),
            "role": row.get("role") or "user",
            "access_tier": _hub_access_tier(row),
            "banned": _hub_user_is_banned(row),
            "joined_at": row.get("created_at"),
        }


@app.put("/api/mt5/admin/users/{username}/ban")
def admin_user_ban(username: str, request: Request, payload: dict[str, Any] = Body(...)):
    admin = _require_admin(request)
    target = username.strip().lower()
    banned = payload.get("banned") is True
    with _HUB_USERS_LOCK:
        users = _load_hub_users()
        row = next(
            (
                item for item in users["users"]
                if str(item.get("username") or "").strip().lower() == target
            ),
            None,
        )
        if not row:
            raise HTTPException(status_code=404, detail="MT5 Hub user was not found.")
        if str(row.get("role") or "user") == "admin":
            raise HTTPException(status_code=409, detail="Administrator accounts cannot be banned.")
        row["banned"] = banned
        if banned:
            row["banned_at"] = datetime.now(timezone.utc).isoformat()
            row["banned_by"] = str(admin.get("username") or ADMIN_RESERVED_USERNAME)
        else:
            row["banned_at"] = None
            row["banned_by"] = None
        _save_hub_users(users)
        return {
            "username": row.get("username"),
            "role": row.get("role") or "user",
            "access_tier": _hub_access_tier(row),
            "banned": _hub_user_is_banned(row),
            "banned_at": row.get("banned_at"),
            "banned_by": row.get("banned_by"),
            "joined_at": row.get("created_at"),
        }


@app.get("/api/mt5/journal/{account_login}")
def journal(account_login: int, year: int | None = None, month: int | None = None, view: str = "month"):
    today = journal_manager.journal_today()
    target_year = int(year or today.year)
    if target_year < 2010 or target_year > today.year + 1:
        raise HTTPException(status_code=400, detail="Unsupported journal year.")
    try:
        if str(view).lower() == "year":
            return journal_manager.year_view(account_login, target_year)
        target_month = int(month or today.month)
        return journal_manager.month_view(account_login, target_year, target_month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/mt5/admin/backtests")
def admin_backtests(request: Request):
    _require_admin(request)
    return backtest_manager.all_jobs()


@app.get("/api/mt5/admin/research")
def admin_research(request: Request):
    _require_admin(request)
    return backtest_manager.all_research()


@app.post("/api/mt5/admin/research/{item_id}/decision")
def admin_research_decision(item_id: str, request: Request, payload: dict[str, Any] = Body(default_factory=dict)):
    _require_admin(request)
    try:
        return backtest_manager.decide_research(
            item_id,
            str(payload.get("decision") or ""),
            str(payload.get("note") or "") or None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Research item was not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def fail(exc: Exception, status: int = 400):
    raise HTTPException(status_code=status, detail=str(exc))


def normalize_http_errors(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except RuntimeError as exc:
        fail(exc, 409)
    except Exception as exc:
        fail(exc, 500)


def session_error(exc: Exception):
    message = str(exc)
    lowered = message.lower()
    if "ipc timeout" in lowered or "worker timeout" in lowered or "timed out" in lowered:
        raise HTTPException(status_code=504, detail=message)
    if any(text in lowered for text in ("authorization", "wrong password", "invalid account", "auth failed")):
        raise HTTPException(status_code=401, detail=message)
    if "otp" in lowered or "certificate" in lowered:
        raise HTTPException(status_code=428, detail=message)
    if "disconnected" in lowered or "not connected" in lowered or "no mt5 account session" in lowered:
        raise HTTPException(status_code=503, detail=message)
    raise HTTPException(status_code=400, detail=message)


def session_snapshot() -> dict[str, Any]:
    try:
        return multi_account_client.accounts()
    except RuntimeError:
        return {"accounts": [], "master": None, "slaves": [], "offline": True}


def _run_ai_trial_scan(payload: AiTrialScanPayload) -> dict[str, Any]:
    exec_tf = str(payload.execution_timeframe).upper()
    bias_tf = str(payload.bias_timeframe).upper()
    execution_rows = multi_account_client.account_request(
        payload.account_login,
        f"/candles/{quote(payload.symbol)}?timeframe={quote(exec_tf)}&count=700",
        timeout=20,
    )
    bias_rows = multi_account_client.account_request(
        payload.account_login,
        f"/candles/{quote(payload.symbol)}?timeframe={quote(bias_tf)}&count=350",
        timeout=20,
    )
    previous = load_ai_trial_snapshot()
    snapshot = run_human_apostle_trial(
        execution_rows,
        bias_rows,
        symbol=payload.symbol,
        account_login=payload.account_login,
        execution_timeframe=exec_tf,
        bias_timeframe=bias_tf,
    )
    snapshot.setdefault("execution_mode", "SIGNAL_ONLY")
    snapshot.setdefault("execution_lock", "live_requires_explicit_confirmation")
    same_context = (
        previous
        and int(previous.get("account_login") or 0) == int(payload.account_login)
        and str(previous.get("symbol") or "") == payload.symbol
        and str(previous.get("execution_timeframe") or "M15").upper() == exec_tf
        and str(previous.get("bias_timeframe") or "H4").upper() == bias_tf
    )
    if same_context:
        snapshot["last_execution"] = previous.get("last_execution")
    else:
        snapshot.setdefault("last_execution", None)
    return save_ai_trial_snapshot(snapshot)


def _ai_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ai_signal_key(snapshot: dict[str, Any]) -> str:
    trade_plan = snapshot.get("proposed_trade") or {}
    return ":".join([
        str(int(snapshot.get("account_login") or 0)),
        str(snapshot.get("symbol") or "").upper(),
        str(snapshot.get("execution_timeframe") or "M15").upper(),
        str(snapshot.get("bias_timeframe") or "H4").upper(),
        str(int(trade_plan.get("time") or 0)),
        str(trade_plan.get("direction") or snapshot.get("decision") or "").upper(),
    ])


def _ai_execution_lock(workspace_id: str) -> threading.RLock:
    with _AI_SCANNERS_LOCK:
        return _AI_EXECUTION_LOCKS.setdefault(workspace_id, threading.RLock())


def _ai_event(event: str, **extra: Any) -> None:
    row = {"time": _ai_now(), "event": event, **extra}
    def mut(state):
        events = state.setdefault("ai_auto_events", [])
        events.insert(0, row)
        del events[100:]
        return row
    update_state(mut)


def _ai_runtime(**updates: Any) -> dict[str, Any]:
    def mut(state):
        runtime = state.setdefault("ai_auto_runtime", {})
        runtime.update(updates)
        return dict(runtime)
    return update_state(mut)


def _connected_ai_account(login: int, *, allow_live: bool = False) -> dict[str, Any]:
    # Verify account mode from the authoritative per-account worker. MT5 trade_mode
    # 2 is a real-money account. LIVE execution requires an explicit confirmation
    # on the specific request that enables/submits the trade.
    workers = multi_account_client.connected_by_login()
    worker = workers.get(int(login))
    if not worker:
        raise RuntimeError(f"MT5 account #{login} is disconnected. AI will keep waiting for it to reconnect.")
    info = dict(worker.get("account_info") or {})
    if bool(info.get("read_only")) or str(info.get("access_mode") or "").lower() == "investor":
        raise PermissionError("AI execution is blocked on investor/read-only MT5 accounts.")
    trade_mode = info.get("trade_mode")
    if trade_mode is None:
        raise PermissionError("KOOLKID could not verify the MT5 account mode. AI execution remains locked.")
    try:
        if isinstance(trade_mode, bool) or str(trade_mode) not in {"0", "1", "2"}:
            raise ValueError("Unknown account mode")
        is_live = int(trade_mode) == 2
    except (TypeError, ValueError):
        raise PermissionError("KOOLKID could not verify the MT5 account mode. AI execution remains locked.")
    if is_live and not allow_live:
        raise PermissionError("LIVE AI execution requires explicit confirmation of the real-money risk warning.")
    account = next((row for row in accounts() if int(row.get("login") or 0) == int(login)), None) or {}
    return {**account, "status": "connected", "account_type": "live" if is_live else "demo", "worker": worker}


def _record_signal_attempt(signal_key: str, snapshot: dict[str, Any], volume: float, source: str) -> None:
    record = {
        "signal_key": signal_key,
        "status": "submitting",
        "attempted_at": _ai_now(),
        "account_login": int(snapshot.get("account_login") or 0),
        "symbol": str(snapshot.get("symbol") or ""),
        "direction": str((snapshot.get("proposed_trade") or {}).get("direction") or snapshot.get("decision") or ""),
        "signal_time": int((snapshot.get("proposed_trade") or {}).get("time") or 0),
        "volume": float(volume),
        "source": source,
    }
    def mut(state):
        registry = state.setdefault("ai_signal_attempts", {})
        registry[signal_key] = record
        if len(registry) > 250:
            oldest = sorted(registry.items(), key=lambda item: str((item[1] or {}).get("attempted_at") or ""))[: len(registry) - 250]
            for key, _ in oldest:
                registry.pop(key, None)
        return record
    update_state(mut)


def _finish_signal_attempt(signal_key: str, status: str, **extra: Any) -> None:
    def mut(state):
        registry = state.setdefault("ai_signal_attempts", {})
        row = registry.setdefault(signal_key, {"signal_key": signal_key})
        row.update({"status": status, "finished_at": _ai_now(), **extra})
        return dict(row)
    update_state(mut)


def _execute_apostle_snapshot(
    snapshot: dict[str, Any],
    volume: float,
    *,
    source: str,
    allow_live: bool = False,
    expected_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if snapshot.get("decision") not in {"BUY", "SELL"} or not snapshot.get("proposed_trade"):
        raise HTTPException(status_code=409, detail="The current Apostle result is not a tradable BUY/SELL signal.")
    login = int(snapshot.get("account_login") or 0)
    symbol = str(snapshot.get("symbol") or "")
    signal_key = _ai_signal_key(snapshot)
    workspace_id = current_workspace()
    with _ai_execution_lock(workspace_id):
        prior = (read_state().get("ai_signal_attempts") or {}).get(signal_key)
        if prior:
            raise HTTPException(status_code=409, detail="This Apostle completed-candle signal was already submitted once. KOOLKID will not duplicate it.")
        fresh = _run_ai_trial_scan(AiTrialScanPayload(
            account_login=login,
            symbol=symbol,
            execution_timeframe=str(snapshot.get("execution_timeframe") or "M15").upper(),
            bias_timeframe=str(snapshot.get("bias_timeframe") or "H4").upper(),
        ))
        if fresh.get("decision") not in {"BUY", "SELL"} or not fresh.get("proposed_trade") or _ai_signal_key(fresh) != signal_key:
            raise HTTPException(status_code=409, detail="The Apostle setup changed before execution. Run a fresh scan.")
        snapshot = fresh
        trade_plan = snapshot["proposed_trade"]
        direction = str(trade_plan.get("direction") or "").upper()
        prices = [float(trade_plan.get(key) or 0) for key in ("entry", "sl", "tp")]
        entry, sl, tp = prices
        if not math.isfinite(float(volume)) or volume <= 0 or not all(math.isfinite(p) and p > 0 for p in prices) or not (
            direction == "BUY" and sl < entry < tp or direction == "SELL" and tp < entry < sl
        ):
            raise HTTPException(status_code=409, detail="The Apostle trade has invalid size or protective prices.")
        execution_account = _connected_ai_account(login, allow_live=allow_live)
        if source == "ai_auto_human_apostle":
            active = read_state().get("ai_auto_config") or {}
            if not expected_config or not active.get("enabled") or active != expected_config:
                raise HTTPException(status_code=409, detail="AI automation stopped or settings changed during the scan.")
        # Mark before order submission. Even if the broker response is ambiguous, the same
        # completed-candle signal is never retried automatically and can never double-fire.
        _record_signal_attempt(signal_key, snapshot, volume, source)
        try:
            result = trade(TradePayload(
                account_login=login,
                symbol=symbol,
                type=str(trade_plan.get("direction") or "BUY").lower(),
                volume=float(volume),
                sl=float(trade_plan.get("sl") or 0),
                tp=float(trade_plan.get("tp") or 0),
                source=source,
                confirm_live=bool(allow_live),
            ))
            if not isinstance(result, dict) or result.get("retcode") not in {10009, 10010} or not any(result.get(k) for k in ("ticket", "deal", "order")):
                raise HTTPException(status_code=409, detail="MT5 did not confirm an AI fill. Check positions before submitting a new signal.")
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc)
            _finish_signal_attempt(signal_key, "failed", error=str(detail))
            raise

        account_type = str(execution_account.get("account_type") or "demo").lower()
        execution_record = {
            "executed": True,
            "account_login": login,
            "account_type": account_type,
            "symbol": symbol,
            "volume": float(volume),
            "direction": trade_plan.get("direction"),
            "executed_at": _ai_now(),
            "signal_time": int(trade_plan.get("time") or 0),
            "signal_key": signal_key,
            "mode": "LIVE_AUTO_TRADE" if account_type == "live" else "DEMO_AUTO_TRADE",
            "automatic": source == "ai_auto_human_apostle",
            "source": source,
            "result": result,
            "message": ("LIVE order submitted" if account_type == "live" else "Demo order submitted")
                + (" automatically by Human Apostle." if source == "ai_auto_human_apostle" else " from the current Apostle signal."),
        }
        _finish_signal_attempt(signal_key, "executed", result=result)
        snapshot["execution_mode"] = execution_record["mode"]
        snapshot["last_execution"] = execution_record
        snapshot["execution"] = f"{account_type.upper()} execution sent to MT5."
        save_ai_trial_snapshot(snapshot)
        return execution_record


def _run_ai_auto_cycle(config: dict[str, Any]) -> None:
    login = int(config.get("account_login") or 0)
    symbol = str(config.get("symbol") or "").strip()
    volume = float(config.get("volume") or 0)
    if not login or not symbol or volume <= 0:
        raise RuntimeError("AI Auto-Trading configuration is incomplete.")
    allow_live = bool(config.get("allow_live"))
    _connected_ai_account(login, allow_live=allow_live)
    snapshot = _run_ai_trial_scan(AiTrialScanPayload(
        account_login=login,
        symbol=symbol,
        execution_timeframe=str(config.get("execution_timeframe") or "M15").upper(),
        bias_timeframe=str(config.get("bias_timeframe") or "H4").upper(),
    ))
    now = _ai_now()
    runtime = {
        "status": "running",
        "last_scan_at": now,
        "last_symbol": symbol,
        "last_decision": snapshot.get("decision"),
        "last_confidence": snapshot.get("confidence"),
        "last_error": None,
    }
    _ai_runtime(**runtime)

    if snapshot.get("decision") not in {"BUY", "SELL"} or not snapshot.get("proposed_trade"):
        return

    signal_key = _ai_signal_key(snapshot)
    _ai_runtime(last_signal_at=now, last_signal_key=signal_key, last_signal=str(snapshot.get("decision")))
    registry = read_state().get("ai_signal_attempts") or {}
    if signal_key in registry:
        return
    try:
        execution = _execute_apostle_snapshot(
            snapshot, volume, source="ai_auto_human_apostle", allow_live=allow_live,
            expected_config=config,
        )
    except HTTPException as exc:
        if exc.status_code == 409 and "already submitted" in str(exc.detail).lower():
            return
        raise
    _ai_runtime(last_execution_at=execution["executed_at"], last_execution=execution, status="running")
    _ai_event("auto_trade_executed", symbol=symbol, direction=execution.get("direction"), signal_time=execution.get("signal_time"), volume=volume)


def _stop_ai_scanner(workspace_id: str) -> None:
    with _AI_SCANNERS_LOCK:
        event = _AI_SCANNER_STOPS.get(workspace_id)
        if event:
            event.set()


def _start_ai_scanner(workspace_id: str) -> None:
    with _AI_SCANNERS_LOCK:
        existing = _AI_SCANNERS.get(workspace_id)
        if existing and existing.is_alive():
            return
        stop_event = threading.Event()
        _AI_SCANNER_STOPS[workspace_id] = stop_event

        def scan_loop():
            context_token = set_workspace(workspace_id)
            try:
                _ai_runtime(status="starting", started_at=_ai_now(), last_error=None)
                while not stop_event.is_set():
                    state = read_state()
                    config = state.get("ai_auto_config") or {}
                    if not config.get("enabled"):
                        _ai_runtime(status="stopped", stopped_at=_ai_now())
                        return
                    interval = max(15, min(int(config.get("scan_seconds") or 30), 300))
                    try:
                        _run_ai_auto_cycle(config)
                    except PermissionError as exc:
                        _ai_runtime(status="blocked", last_error=str(exc), last_error_at=_ai_now())
                    except Exception as exc:
                        detail = getattr(exc, "detail", None) or str(exc)
                        _ai_runtime(status="waiting", last_error=str(detail), last_error_at=_ai_now())
                    if stop_event.wait(interval):
                        break
                _ai_runtime(status="stopped", stopped_at=_ai_now())
            finally:
                reset_workspace(context_token)
                with _AI_SCANNERS_LOCK:
                    if _AI_SCANNERS.get(workspace_id) is threading.current_thread():
                        _AI_SCANNERS.pop(workspace_id, None)
                        _AI_SCANNER_STOPS.pop(workspace_id, None)

        thread = threading.Thread(target=scan_loop, daemon=True, name=f"KOOLKID-AI-Scan-{workspace_id[:8]}")
        _AI_SCANNERS[workspace_id] = thread
        thread.start()


def _ai_auto_status() -> dict[str, Any]:
    workspace_id = current_workspace()
    state = read_state()
    config = dict(state.get("ai_auto_config") or {})
    runtime = dict(state.get("ai_auto_runtime") or {})
    with _AI_SCANNERS_LOCK:
        thread = _AI_SCANNERS.get(workspace_id)
        alive = bool(thread and thread.is_alive())
    enabled = bool(config.get("enabled"))
    if not enabled and not alive:
        runtime["status"] = "stopped"
    return {
        "strategy": "Human Apostle",
        "execution_lock": "live_requires_explicit_confirmation",
        "execution_timeframe": str(config.get("execution_timeframe") or "M15"),
        "bias_timeframe": str(config.get("bias_timeframe") or "H4"),
        "enabled": enabled,
        "scanner_alive": alive,
        "config": config,
        "runtime": runtime,
        "events": list(state.get("ai_auto_events") or [])[:50],
    }


def _mark_library_revision_running(
    bot_id: int,
    revision: str,
    assignment: dict[str, Any] | None = None,
    *,
    previous_revision: str | None = None,
    restarted: bool = False,
    error: str | None = None,
) -> dict[str, Any] | None:
    def mut(state):
        row = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == int(bot_id)), None)
        if not row:
            return None
        row["running_library_revision"] = revision
        row["library_update_error"] = error
        if restarted:
            row["last_library_restart_at"] = datetime.now(timezone.utc).isoformat()
            row["last_library_restart_from"] = previous_revision
            row["last_library_restart_to"] = revision
        if assignment:
            row.update({
                "status": assignment.get("status", "running"),
                "started_at": assignment.get("started_at"),
                "worker_id": assignment.get("worker_id"),
                "terminal_id": assignment.get("terminal_id"),
                "process_id": assignment.get("process_id"),
                "terminal_status": assignment.get("terminal_status"),
                "last_activity": assignment.get("last_activity"),
                "last_error": assignment.get("error"),
                "ea_verified": assignment.get("ea_verified", False),
                "ea_status": assignment.get("ea_status"),
                "account_verified": assignment.get("account_verified", False),
                "open_positions": assignment.get("open_positions", 0),
                "current_pl": assignment.get("current_pl", 0),
                "today_pl": assignment.get("today_pl", 0),
            })
        return dict(row)
    return update_state(mut)


def _library_restart_payload(bot: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    payload = dict(assignment.get("restart_request") or {})
    if not payload:
        raise RuntimeError("Running EA does not have a saved restart request.")
    ea_rel = bot.get("ea_storage_path")
    if ea_rel:
        ea_path = (ROOT / str(ea_rel)).resolve()
        if not ea_path.is_file():
            raise RuntimeError("Updated EA file is missing from the Bot Library.")
        payload["ea_path"] = str(ea_path)
        payload["ea_filename"] = bot.get("ea_filename") or ea_path.name
    preset_rel = bot.get("preset_storage_path")
    payload["preset_path"] = str((ROOT / str(preset_rel)).resolve()) if preset_rel else None
    payload["preset_filename"] = bot.get("preset_filename")
    payload["configured_magic"] = int((bot.get("settings") or {}).get("magic_number") or 0) or None
    return payload


def _force_restart_library_bot(bot: dict[str, Any], assignment: dict[str, Any] | list[dict[str, Any]], desired_revision: str) -> dict[str, Any]:
    bot_id = int(bot.get("id") or 0)
    previous_revision = str(bot.get("running_library_revision") or "") or None
    assignment_rows = assignment if isinstance(assignment, list) else [assignment]
    payloads = [_library_restart_payload(bot, row) for row in assignment_rows]
    # Intentionally do not inspect open_positions. Library updates force an immediate
    # terminal/EA restart even while broker positions remain open.
    ea_worker_client.request(f"/bots/{bot_id}/stop", "POST", {}, timeout=20)
    restarted_rows: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            restarted_rows.append(ea_worker_client.request("/bots/start", "POST", payload, timeout=120))
        except RuntimeError:
            time.sleep(1.0)
            restarted_rows.append(ea_worker_client.request("/bots/start", "POST", payload, timeout=120))
    restarted = restarted_rows[0] if len(restarted_rows) == 1 else {
        **restarted_rows[0],
        "instances": restarted_rows,
        "symbols": [row.get("symbol") for row in restarted_rows],
    }
    _mark_library_revision_running(
        bot_id,
        desired_revision,
        restarted,
        previous_revision=previous_revision,
        restarted=True,
    )
    return restarted


def _reconcile_library_updates(workspace_id: str) -> None:
    with _library_update_lock(workspace_id):
        token = set_workspace(workspace_id)
        try:
            state = read_state()
            try:
                assignments: dict[int, list[dict[str, Any]]] = {}
                for row in ea_worker_client.request("/bots", timeout=8):
                    if row.get("status") not in {"starting", "running"}:
                        continue
                    assignments.setdefault(int(row.get("bot_id") or 0), []).append(row)
            except RuntimeError:
                assignments = {}

            for bot in state.get("bots", []):
                bot_id = int(bot.get("id") or 0)
                desired_revision = str(bot.get("library_revision") or bot_library_revision(bot) or "")
                if not desired_revision:
                    continue

                if bot.get("native_engine"):
                    config = dict(bot.get("native_config") or {})
                    if not config.get("enabled"):
                        continue
                    # Native strategy threads are recreated by the bridge on deploy/startup,
                    # so the newly loaded strategy code is already active.
                    _mark_library_revision_running(
                        bot_id,
                        desired_revision,
                        previous_revision=str(bot.get("running_library_revision") or "") or None,
                        restarted=bool(bot.get("running_library_revision") and bot.get("running_library_revision") != desired_revision),
                    )
                    continue

                assignment_rows = assignments.get(bot_id)
                if not assignment_rows:
                    continue

                running_revision = str(bot.get("running_library_revision") or "")
                if not running_revision:
                    # First rollout of revision tracking: adopt the current running build
                    # as the baseline without bouncing an existing user's EA.
                    _mark_library_revision_running(bot_id, desired_revision, assignment_rows[0])
                    continue
                if running_revision == desired_revision:
                    continue
                try:
                    _force_restart_library_bot(bot, assignment_rows, desired_revision)
                except Exception as exc:
                    def mark_error(current_state):
                        row = next((b for b in current_state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
                        if row:
                            row["library_update_error"] = str(exc)
                            row["last_error"] = f"Library update restart failed: {exc}"
                        return dict(row) if row else None
                    update_state(mark_error)
        finally:
            reset_workspace(token)


def _schedule_library_update_reconcile(workspace_id: str) -> None:
    threading.Thread(
        target=_reconcile_library_updates,
        args=(workspace_id,),
        daemon=True,
        name=f"KOOLKID-Library-Update-{workspace_id[:8]}",
    ).start()


@app.on_event("startup")
def restore_ai_scanners():
    for workspace_id in workspace_ids(HUB_USERS_FILE):
        token = set_workspace(workspace_id)
        try:
            config = read_state().get("ai_auto_config") or {}
            if config.get("enabled"):
                _start_ai_scanner(workspace_id)
            ai_auto_select.restore(workspace_id)
            native_runtime.restore(workspace_id)
        finally:
            reset_workspace(token)
        _schedule_library_update_reconcile(workspace_id)


@app.get("/")
def root():
    return {"name": "KOOLKID Local MT5 Bridge", "status": "ok", "docs": "/docs"}


@app.get("/health")
def health():
    account_worker = multi_account_client.public_status()
    ea_worker = ea_worker_client.public_status()
    return {
        "ok": True,
        "revision": "mt5-bridge-ea-v6",
        "time": datetime.now(timezone.utc).isoformat(),
        "copy_worker": account_worker["status"],
        "account_worker": account_worker,
        "ea_worker": ea_worker,
    }


@app.get("/api/mt5/bridge/status")
def bridge_status():
    worker = ea_worker_client.status()
    snapshot = session_snapshot()
    copy_online = not bool(snapshot.get("offline"))
    connected = [row for row in snapshot.get("accounts", []) if row.get("connected")]
    return {
        "status": "online", "mode": "bridge", "terminal": None, "terminal_path": None, "data_path": None,
        "endpoint": "http://127.0.0.1:8000", "protocol": "http",
        "trading_enabled": bool(connected), "account_login": None, "account_server": None,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "message": f"MT5 coordinator online. {len(connected)} verified account session(s).",
        "services": {"bridge": "online", "ea_worker": worker["status"], "copy_worker": "online" if copy_online else "offline"},
        "capabilities": {"account_data": copy_online, "quotes": bool(connected), "candles": bool(connected), "manual_trading": bool(connected), "positions": copy_online, "history": bool(connected), "ea_launch": worker["status"] == "online", "mq5_compile": mq5_compiler.compiler_status()["available"]},
        "compiler": mq5_compiler.compiler_status(),
        "ea_worker": worker,
    }


@app.get("/api/mt5/preferences")
def get_hub_preferences():
    return dict(read_state().get("hub_preferences") or {})


@app.put("/api/mt5/preferences")
def save_hub_preferences(payload: dict[str, Any] = Body(default_factory=dict)):
    allowed_brokers = {"all", "current", "deriv", "weltrade", "favorites", "custom"}
    allowed_categories = {
        "all", "synthetic", "forex", "metals", "indices", "crypto", "stocks", "energies",
        "weltrade_syntx", "fxvol", "sfxvol", "painx", "gainx", "flipx",
        "switchx", "breakx", "trendx", "progression", "maxx", "custom",
    }
    def mut(state):
        current = dict(state.get("hub_preferences") or {})
        current.update({k: v for k, v in payload.items() if k in {
            "pollMs", "confirmDanger", "restoreWorkspace", "reconnectOnStartup", "notifications",
            "marketBrokerFilter", "marketCategoryFilter", "customBrokerFamilies", "customMarketGroups", "marketFavorites",
        }})
        if current.get("marketBrokerFilter") not in allowed_brokers:
            current["marketBrokerFilter"] = "all"
        if current.get("marketCategoryFilter") not in allowed_categories:
            current["marketCategoryFilter"] = "all"
        current["customBrokerFamilies"] = [
            item for item in current.get("customBrokerFamilies", []) if item in {"deriv", "weltrade", "other"}
        ] or ["deriv", "weltrade", "other"]
        valid_groups = {"synthetic", "forex", "metals", "indices", "crypto", "stocks", "energies", "weltrade_syntx"}
        current["customMarketGroups"] = [
            item for item in current.get("customMarketGroups", []) if item in valid_groups
        ] or list(valid_groups)
        favorites = current.get("marketFavorites")
        if not isinstance(favorites, dict):
            favorites = {}
        current["marketFavorites"] = {
            str(scope)[:32]: [str(symbol)[:64] for symbol in symbols[:32] if str(symbol).strip()]
            for scope, symbols in favorites.items()
            if isinstance(symbols, list)
        }
        state["hub_preferences"] = current
        return dict(current)
    return update_state(mut)


@app.get("/api/mt5/accounts")
def accounts():
    rows = engine.list_accounts()
    snapshot = session_snapshot()
    try:
        known = {int(row.get("login") or 0) for row in rows}
        for saved in snapshot.get("accounts", []):
            login = int(saved.get("login") or 0)
            if not login or login in known:
                continue
            engine.upsert_profile({
                "login": login, "nickname": saved.get("nickname") or f"MT5 #{login}",
                "broker": saved.get("broker") or "MetaTrader 5", "server": saved.get("server") or "",
                "access_mode": saved.get("access_mode") or "trading", "balance": 0,
                "equity": 0, "margin": 0, "free_margin": 0, "floating_pl": 0,
                "leverage": 0, "currency": "USD", "status": "disconnected",
                "is_active": False, "account_type": "demo", "connection_status": "offline",
            }, make_active=False)
        rows = engine.list_accounts()
    except Exception:
        pass
    sessions = {int(item.get("login") or 0): item for item in snapshot.get("accounts", [])}
    for row in rows:
        session = sessions.get(int(row.get("login") or 0))
        if session:
            info = session.get("account_info") or {}
            row["budget"] = session.get("budget")
            row["budget_enabled"] = bool(session.get("budget_enabled") or session.get("budget") is not None)
            row["access_mode"] = session.get("access_mode") or info.get("access_mode") or row.get("access_mode") or "trading"
            row["read_only"] = bool(info.get("read_only") or row["access_mode"] == "investor")
        else:
            row["budget_enabled"] = bool(row.get("budget_enabled") and row.get("budget") is not None)
        if not session or not session.get("connected"):
            row.update({"status": "connecting" if session and session.get("connecting") else "disconnected", "connection_status": "offline", "worker_id": None, "cached": True})
            continue
        info = session.get("account_info") or {}
        row.update({
            "status": "connected", "connection_status": "online", "worker_id": session.get("account_id"), "cached": False,
            "balance": float(info.get("balance") or row.get("balance") or 0),
            "equity": float(info.get("equity") or row.get("equity") or 0),
            "margin": float(info.get("margin") or 0), "free_margin": float(info.get("margin_free") or 0),
            "floating_pl": float(info.get("profit") or 0), "leverage": int(info.get("leverage") or row.get("leverage") or 0),
            "currency": info.get("currency") or row.get("currency") or "USD",
            "account_type": "live" if int(info.get("trade_mode") or 0) == 2 else "demo",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        })
    return rows


@app.post("/api/mt5/accounts/test")
def test_account(payload: AccountPayload):
    if not payload.password:
        raise HTTPException(status_code=400, detail="MT5 password is required for a connection test.")
    access_mode = "investor" if str(payload.access_mode or "").lower() == "investor" else "trading"
    profile = {"login": payload.login, "nickname": payload.nickname or f"MT5 #{payload.login}", "server": payload.server or "", "broker": payload.broker or "MetaTrader 5", "access_mode": access_mode}
    try:
        engine.shutdown_terminal()
        result = multi_account_client.connect(profile, payload.password)
        mode_label = "investor/read-only" if access_mode == "investor" else "trading"
        return {"ok": True, "mode": "bridge", "message": f"Connected to {payload.server or 'MT5'} as #{payload.login} using {mode_label} access.", "session": result}
    except RuntimeError as exc:
        session_error(exc)


@app.post("/api/mt5/accounts/connect")
def connect_account(payload: AccountPayload):
    if not payload.password:
        raise HTTPException(status_code=400, detail="MT5 password is required when adding a new account. KOOLKID does not persist it.")
    access_mode = "investor" if str(payload.access_mode or "").lower() == "investor" else "trading"
    profile = {"login": payload.login, "nickname": payload.nickname or f"MT5 #{payload.login}", "server": payload.server or "", "broker": payload.broker or "MetaTrader 5", "access_mode": access_mode}
    try:
        engine.shutdown_terminal()
        session = multi_account_client.connect(profile, payload.password or "")
    except RuntimeError as exc:
        session_error(exc)
    info = session.get("account_info") or {}
    profile.update({"balance": float(info.get("balance") or 0), "equity": float(info.get("equity") or 0), "margin": float(info.get("margin") or 0), "free_margin": float(info.get("margin_free") or 0), "floating_pl": float(info.get("profit") or 0), "leverage": int(info.get("leverage") or 0), "currency": info.get("currency") or "USD", "status": "connected", "connection_status": "online", "account_type": "live" if int(info.get("trade_mode") or 0) == 2 else "demo", "access_mode": access_mode, "read_only": access_mode == "investor"})
    engine.upsert_profile(profile)
    return next((row for row in accounts() if int(row.get("login", 0)) == payload.login), profile)


@app.post("/api/mt5/accounts/connect/cancel")
def cancel_account_connect(payload: dict[str, Any] = Body(...)):
    login = int(payload.get("login") or 0)
    if not login:
        raise HTTPException(status_code=400, detail="MT5 login is required to cancel a connection.")
    try:
        result = multi_account_client.request(f"/accounts/session-{login}/cancel", "POST", {}, timeout=5)
        return {"ok": bool(result.get("ok"))}
    except RuntimeError as exc:
        session_error(exc)


@app.put("/api/mt5/accounts/{profile_id}/budget")
def set_account_budget(profile_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    profile = next((x for x in state.get("profiles", []) if int(x.get("id", 0)) == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found.")
    login = int(profile.get("login") or 0)
    try:
        result = multi_account_client.request(
            f"/accounts/session-{login}/budget", "PUT",
            {"budget": payload.get("budget"), "reset": bool(payload.get("reset"))}, timeout=10,
        )
    except RuntimeError as exc:
        session_error(exc)
    updated = dict(profile)
    updated["budget"] = result.get("budget")
    updated["budget_enabled"] = bool(result.get("budget_enabled"))
    updated["budget_virtual_balance"] = result.get("virtual_balance")
    updated["budget_virtual_equity"] = result.get("virtual_equity")
    updated["budget_virtual_free_margin"] = result.get("virtual_free_margin")
    upsert_profile(updated, make_active=False)
    row = next((x for x in accounts() if int(x.get("id", 0)) == profile_id), updated)
    return {**row, **{k: v for k, v in result.items() if k.startswith("budget") or k.startswith("virtual_") or k.startswith("actual_") or k == "margin_used"}}


@app.delete("/api/mt5/accounts/{profile_id}")
def delete_account(profile_id: int):
    state = read_state()
    profile = next((x for x in state.get("profiles", []) if int(x.get("id", 0)) == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found.")
    try:
        multi_account_client.remove(int(profile.get("login", 0)))
    except RuntimeError:
        pass
    return {"ok": remove_profile(profile_id)}


@app.put("/api/mt5/accounts/{profile_id}")
def account_action(profile_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    profile = next((x for x in state.get("profiles", []) if int(x.get("id", 0)) == profile_id), None)
    if not profile:
        raise HTTPException(status_code=404, detail="Account profile not found.")
    action = str(payload.get("action") or "")
    login = int(profile.get("login", 0))
    if action == "set_active":
        engine.set_active_login(login)
        return next((x for x in accounts() if int(x["id"]) == profile_id), profile)
    if action in {"toggle", "connect", "disconnect"}:
        live = {int(row.get("login") or 0): row for row in session_snapshot().get("accounts", []) if row.get("connected")}
        should_disconnect = action == "disconnect" or (action == "toggle" and login in live)
        if should_disconnect:
            try:
                multi_account_client.disconnect(login)
            except RuntimeError:
                pass
        elif login not in live:
            password = str(payload.get("password") or "") or None
            try:
                engine.shutdown_terminal()
                multi_account_client.connect(profile, password or "")
            except RuntimeError as exc:
                session_error(exc)
        return next((x for x in accounts() if int(x["id"]) == profile_id), profile)
    if action == "cancel_connect":
        try:
            result = multi_account_client.request(f"/accounts/session-{login}/cancel", "POST", {}, timeout=5)
            return {"ok": bool(result.get("ok"))}
        except RuntimeError as exc:
            session_error(exc)
    raise HTTPException(status_code=400, detail=f"Unsupported account action '{action}'.")


@app.get("/api/mt5/quotes")
def get_quotes(symbols: str = Query(default=""), account_login: int | None = None):
    requested = [x.strip() for x in symbols.split(",") if x.strip()]
    if not requested:
        return []
    if not account_login:
        raise HTTPException(status_code=422, detail="Select a connected MT5 account before requesting quotes.")
    try:
        return multi_account_client.account_request(account_login, f"/quotes?symbols={quote(','.join(requested))}", timeout=5)
    except RuntimeError as exc:
        message = str(exc)
        raise HTTPException(status_code=504 if "timeout" in message.lower() else 503, detail=message)


@app.get("/api/mt5/candles/{symbol}")
def get_candles(symbol: str, timeframe: str = "M15", count: int = 220, account_login: int | None = None):
    try:
        return multi_account_client.account_request(account_login, f"/candles/{quote(symbol)}?timeframe={quote(timeframe)}&count={count}", timeout=15)
    except RuntimeError as exc:
        session_error(exc)


@app.get("/api/mt5/symbols")
def get_symbols(visible_only: bool = True, limit: int = 1000, account_login: int | None = None):
    try:
        return multi_account_client.account_request(account_login, f"/symbols?visible_only={str(visible_only).lower()}&limit={limit}", timeout=15)
    except RuntimeError as exc:
        session_error(exc)


def _bot_identity_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _bot_for_trade(row: dict[str, Any], bot_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    source = str(row.get("source") or "")
    comment = str(row.get("comment") or "")
    account_login = int(row.get("account_login") or 0)
    native_match = re.search(r"\bKKN(\d+)\b", f"{source} {comment}", re.IGNORECASE)
    if native_match:
        bot_id = int(native_match.group(1))
        matched = next((bot for bot in bot_rows if int(bot.get("id") or 0) == bot_id), None)
        if matched:
            return matched

    candidates = [
        bot for bot in bot_rows
        if not account_login or int(bot.get("account_login") or 0) == account_login
    ]

    mt5_comment_match = re.search(r"KKBOT\(([^)]*)\)", f"{source} {comment}", re.IGNORECASE)
    if mt5_comment_match:
        comment_name = _bot_identity_text(mt5_comment_match.group(1))
        comment_matches = [
            bot for bot in candidates
            if _bot_identity_text(bot.get("name")).startswith(comment_name)
            or comment_name.startswith(_bot_identity_text(bot.get("name")))
        ]
        if len(comment_matches) == 1:
            return comment_matches[0]
    magic = int(row.get("magic") or 0)
    if magic:
        magic_matches = []
        for bot in candidates:
            settings = dict(bot.get("settings") or {})
            configured = int(settings.get("magic_number") or 0)
            detected = int(bot.get("detected_magic") or 0)
            if magic in {configured, detected} and magic not in {0, 990001}:
                magic_matches.append(bot)
        if len(magic_matches) == 1:
            return magic_matches[0]

    source_key = _bot_identity_text(source)
    comment_key = _bot_identity_text(comment)
    name_matches: list[dict[str, Any]] = []
    for bot in candidates:
        identities = {
            _bot_identity_text(bot.get("name")),
            _bot_identity_text(Path(str(bot.get("ea_filename") or "")).stem),
            _bot_identity_text(Path(str(bot.get("source_filename") or "")).stem),
            _bot_identity_text(Path(str(bot.get("native_source") or "")).stem),
        } - {""}
        if source_key in identities or comment_key in identities:
            name_matches.append(bot)
    return name_matches[0] if len(name_matches) == 1 else None


def _enrich_bot_trade_row(row: dict[str, Any], bot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    item = dict(row)
    bot = _bot_for_trade(item, bot_rows)
    if bot:
        item["bot_id"] = int(bot.get("id") or 0)
        item["bot_name"] = str(bot.get("name") or "")
    return item


def _overlay_bot_activity(bot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not bot_rows:
        return bot_rows
    try:
        raw_positions = list(multi_account_client.request("/positions", timeout=8).get("positions", []))
    except RuntimeError:
        raw_positions = []
    try:
        raw_history = list(_history_for_stats(30))
    except Exception:
        raw_history = []

    enriched_positions = [_enrich_bot_trade_row(dict(row), bot_rows) for row in raw_positions]
    enriched_history = [_enrich_bot_trade_row(dict(row), bot_rows) for row in raw_history]
    today = datetime.now(timezone.utc).date()

    for bot in bot_rows:
        bot_id = int(bot.get("id") or 0)
        related_positions = [row for row in enriched_positions if int(row.get("bot_id") or 0) == bot_id]
        related_history = [row for row in enriched_history if int(row.get("bot_id") or 0) == bot_id]

        session_started = None
        session_started_raw = bot.get("session_started_at") or bot.get("started_at")
        if session_started_raw:
            try:
                session_started = datetime.fromisoformat(str(session_started_raw).replace("Z", "+00:00"))
                if session_started.tzinfo is None:
                    session_started = session_started.replace(tzinfo=timezone.utc)
                session_started = session_started.astimezone(timezone.utc)
            except (TypeError, ValueError):
                session_started = None
        if session_started is not None:
            session_history = []
            for row in related_history:
                try:
                    closed = datetime.fromisoformat(str(row.get("close_time") or "").replace("Z", "+00:00"))
                    if closed.tzinfo is None:
                        closed = closed.replace(tzinfo=timezone.utc)
                    if closed.astimezone(timezone.utc) >= session_started:
                        session_history.append(row)
                except (TypeError, ValueError):
                    continue
            related_history = session_history

        bot["open_positions"] = len(related_positions)
        bot["current_pl"] = 0.0
        bot["bot_trade_count"] = 0
        bot["bot_wins"] = 0
        bot["bot_losses"] = 0
        bot["bot_win_rate"] = 0.0
        bot["last_trade"] = None
        bot["today_pl"] = 0.0
        bot["profit_today"] = 0.0
        today_history = []
        for row in related_history:
            try:
                closed = datetime.fromisoformat(str(row.get("close_time") or "").replace("Z", "+00:00"))
                if closed.tzinfo is None:
                    closed = closed.replace(tzinfo=timezone.utc)
                if closed.astimezone(timezone.utc).date() == today:
                    today_history.append(row)
            except (TypeError, ValueError):
                continue

        if related_positions:
            bot["open_positions"] = len(related_positions)
            bot["current_pl"] = round(sum(
                float(row.get("profit") or 0)
                + float(row.get("swap") or 0)
                + float(row.get("commission") or 0)
                for row in related_positions
            ), 2)
        if related_history:
            bot["bot_trade_count"] = len(related_history)
            bot["bot_wins"] = len([row for row in related_history if float(row.get("net_pl") or row.get("profit") or 0) > 0])
            bot["bot_losses"] = len([row for row in related_history if float(row.get("net_pl") or row.get("profit") or 0) < 0])
            bot["bot_win_rate"] = round(bot["bot_wins"] / len(related_history) * 100, 1) if related_history else 0.0
            latest = max(related_history, key=lambda row: str(row.get("close_time") or ""))
            bot["last_trade"] = {
                "ticket": int(latest.get("ticket") or latest.get("id") or 0),
                "symbol": str(latest.get("symbol") or ""),
                "time": str(latest.get("close_time") or ""),
            }
        if today_history:
            realized = round(sum(float(row.get("net_pl") or row.get("profit") or 0) for row in today_history), 2)
            bot["today_pl"] = realized
            bot["profit_today"] = realized
        if related_positions or related_history:
            bot["attribution_status"] = "verified"
            bot["metrics_scope"] = f"Verified KOOLKID bot activity for {str(bot.get('name') or 'this bot')}."
    return bot_rows


@app.get("/api/mt5/positions")
def positions():
    try:
        worker_rows = multi_account_client.request("/positions", timeout=10).get("positions", [])
        if worker_rows:
            bot_rows = list(read_state().get("bots") or [])
            return [_enrich_bot_trade_row(dict(row), bot_rows) for row in worker_rows]
    except RuntimeError:
        pass
    return []


@app.post("/api/mt5/trade")
def trade(payload: TradePayload):
    workers = normalize_http_errors(multi_account_client.connected_by_login)
    worker = workers.get(payload.account_login)
    if worker:
        info = dict(worker.get("account_info") or {})
        if bool(info.get("read_only")) or str(info.get("access_mode") or "").lower() == "investor":
            raise HTTPException(status_code=403, detail="Trading is blocked on investor/read-only MT5 accounts.")
        trade_mode = info.get("trade_mode")
        if trade_mode is None:
            raise HTTPException(status_code=403, detail="KOOLKID could not verify the MT5 account mode.")
        try:
            is_live = int(trade_mode) == 2
        except (TypeError, ValueError):
            raise HTTPException(status_code=403, detail="KOOLKID could not verify the MT5 account mode.")
        if is_live and not payload.confirm_live:
            raise HTTPException(status_code=403, detail="LIVE trading requires explicit confirmation of the testing-phase risk warning.")
        result = normalize_http_errors(lambda: multi_account_client.request("/manual-trade", "POST", {
            "target_account_ids": [worker["account_id"]], "symbol": payload.symbol,
            "side": payload.type.lower(), "volume": payload.volume, "sl": payload.sl or 0, "tp": payload.tp or 0,
            "confirm_live": bool(payload.confirm_live),
        }, timeout=55))
        row = result.get("results", {}).get(worker["account_id"], {})
        if not row.get("ok"):
            raise HTTPException(status_code=409, detail=row.get("error") or "MT5 worker rejected the order.")
        return row.get("result")
    raise HTTPException(status_code=503, detail=f"MT5 account #{payload.account_login} is disconnected.")


@app.post("/api/mt5/positions/{ticket}/close")
def close_position(ticket: int):
    try:
        data = multi_account_client.request("/positions", timeout=10)
        match = next((row for row in data.get("positions", []) if int(row.get("ticket") or 0) == ticket), None)
        if match:
            return normalize_http_errors(lambda: multi_account_client.request("/positions/close", "POST", {"account_id": match["account_id"], "ticket": ticket}, timeout=55))
    except RuntimeError:
        pass
    raise HTTPException(status_code=404, detail=f"Open position #{ticket} was not found in a live account session.")


@app.post("/api/mt5/positions/close-all")
def close_all_positions():
    data = normalize_http_errors(lambda: multi_account_client.request("/positions", timeout=10))
    closed = 0
    errors = []
    for row in data.get("positions", []):
        try:
            multi_account_client.request("/positions/close", "POST", {"account_id": row["account_id"], "ticket": int(row["ticket"])}, timeout=20)
            closed += 1
        except RuntimeError as exc:
            errors.append(str(exc))
    return {"ok": not errors, "closed": closed, "realized": 0, "errors": errors}


def _history_archive_key(row: dict[str, Any]) -> str:
    return ":".join([
        str(row.get("account_login") or ""),
        str(row.get("ticket") or row.get("id") or ""),
        str(row.get("close_time") or ""),
    ])


def _store_history_archive(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return list(read_state().get("history_archive") or [])

    def mutate(state):
        merged = {
            _history_archive_key(dict(row)): dict(row)
            for row in state.get("history_archive", [])
            if isinstance(row, dict) and _history_archive_key(dict(row))
        }
        for row in rows:
            item = dict(row)
            key = _history_archive_key(item)
            if key:
                merged[key] = item
        archive = sorted(
            merged.values(),
            key=lambda item: str(item.get("close_time") or ""),
            reverse=True,
        )[:20000]
        state["history_archive"] = archive
        return archive

    return update_state(mutate)


def _filter_history_archive(rows: list[dict[str, Any]], days: int | None) -> list[dict[str, Any]]:
    if days is None or int(days) <= 0:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    out = []
    for row in rows:
        try:
            closed = datetime.fromisoformat(str(row.get("close_time") or "").replace("Z", "+00:00"))
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            if closed >= cutoff:
                out.append(row)
        except (TypeError, ValueError):
            continue
    return out


@app.get("/api/mt5/history")
def history(days: int | None = None):
    requested_days = int(days or 0)
    state = read_state()
    archive_before = list(state.get("history_archive") or [])
    full_sync_at = float(state.get("history_archive_full_sync_at") or 0)
    full_sync_due = requested_days <= 0 and (
        not archive_before or time.time() - full_sync_at > 6 * 60 * 60
    )
    fetch_days = requested_days if requested_days > 0 else (3650 if full_sync_due else 30)

    bot_rows = list(state.get("bots") or [])
    fetched: list[dict[str, Any]] = []
    for session in session_snapshot().get("accounts", []):
        if not session.get("connected"):
            continue
        try:
            rows = multi_account_client.request(
                f"/accounts/{session['account_id']}/history?days={fetch_days}",
                timeout=20,
            )
            fetched.extend(_enrich_bot_trade_row(dict(row), bot_rows) for row in rows)
        except RuntimeError:
            continue

    archive = _store_history_archive(fetched)
    if full_sync_due:
        update_state(lambda current: current.update({"history_archive_full_sync_at": time.time()}) or True)
    archive = [_enrich_bot_trade_row(dict(row), bot_rows) for row in archive]
    archive.sort(key=lambda row: row.get("close_time", ""), reverse=True)
    return _filter_history_archive(archive, requested_days)


def _history_for_stats(days: int = 30) -> list[dict[str, Any]]:
    sessions = [row for row in session_snapshot().get("accounts", []) if row.get("connected")]
    session_key = ",".join(sorted(str(row.get("account_id") or row.get("login") or "") for row in sessions))
    now = time.monotonic()
    workspace_id = current_workspace()
    with _stats_history_lock:
        cache = _stats_history_cache.get(workspace_id, {})
        if cache.get("session_key") == session_key and now - float(cache.get("loaded_at") or 0) < 15:
            return list(cache.get("rows") or [])
    rows = history(days)
    with _stats_history_lock:
        _stats_history_cache[workspace_id] = {"session_key": session_key, "loaded_at": now, "rows": list(rows)}
    return rows


def _empty_stats():
    state = read_state()
    bots = state.get("bots", [])
    return {
        "kpis": {
            "total_balance": 0, "total_equity": 0, "floating": 0, "margin": 0, "free_margin": 0, "margin_level": None,
            "realized_today": 0, "today_pl": 0, "trades_today": 0, "latest_day": None, "connected_accounts": 0,
            "total_accounts": len(state.get("profiles", [])), "running_bots": 0, "paused_bots": 0, "total_bots": len(bots),
            "open_positions": 0, "win_rate_30d": 0, "trades_30d": 0, "profit_30d": 0, "drawdown_pct": 0, "peak_equity": 0,
        },
        "equity": [], "daily": [], "bots": bots, "symbolPnl": [], "exposure": [],
    }


@app.get("/api/mt5/stats")
def stats():
    base = _empty_stats()
    live_accounts = [row for row in accounts() if row.get("status") == "connected"]
    position_rows = positions()
    history_rows = _history_for_stats(30)
    today = datetime.now(timezone.utc).date().isoformat()
    today_rows = [row for row in history_rows if str(row.get("close_time", "")).startswith(today)]
    kpis = base["kpis"]
    kpis.update({
        "total_balance": sum(float(row.get("balance") or 0) for row in live_accounts),
        "total_equity": sum(float(row.get("equity") or 0) for row in live_accounts),
        "floating": sum(float(row.get("profit") or 0) for row in position_rows),
        "margin": sum(float(row.get("margin") or 0) for row in live_accounts),
        "free_margin": sum(float(row.get("free_margin") or 0) for row in live_accounts),
        "realized_today": sum(float(row.get("net_pl") or 0) for row in today_rows),
        "today_pl": sum(float(row.get("net_pl") or 0) for row in today_rows) + sum(float(row.get("profit") or 0) for row in position_rows),
        "trades_today": len(today_rows), "connected_accounts": len(live_accounts),
        "open_positions": len(position_rows), "trades_30d": len(history_rows),
        "profit_30d": sum(float(row.get("net_pl") or 0) for row in history_rows),
        "win_rate_30d": (100 * len([row for row in history_rows if float(row.get("net_pl") or 0) > 0]) / len(history_rows)) if history_rows else 0,
    })
    return base


@app.get("/api/mt5/risk")
def get_risk():
    state = read_state()
    return state.get("risk") or [default_risk()]


@app.put("/api/mt5/risk")
def put_risk(row: dict[str, Any] = Body(...)):
    required = {"id", "scope", "max_daily_loss", "max_daily_profit", "max_drawdown_pct", "max_lot_size", "max_open_positions", "max_trades_per_day", "max_risk_per_trade", "allowed_trading_hours", "allowed_symbols", "auto_stop"}
    missing = required - set(row)
    if missing:
        raise HTTPException(status_code=400, detail="Missing risk fields: " + ", ".join(sorted(missing)))
    def mut(state):
        rows = state.setdefault("risk", [])
        idx = next((i for i, item in enumerate(rows) if str(item.get("id")) == str(row.get("id"))), -1)
        if idx >= 0:
            rows[idx] = row
        else:
            rows.append(row)
        return row
    return update_state(mut)


@app.get("/api/mt5/copy")
def copy_state():
    state = read_state()
    return {
        "relationships": state.get("copy_relationships", []),
        "events": state.get("copy_events", [])[:500],
        "real_execution_available": False,
        "execution_message": "Copy rules are saved, but real multi-account copying is safety-locked until isolated MT5 terminal workers are installed. Simulation copy trading is fully testable in the frontend runtime.",
    }


@app.post("/api/mt5/copy")
def create_copy(payload: dict[str, Any] = Body(...)):
    master = int(payload.get("master_login") or 0)
    follower = int(payload.get("follower_login") or 0)
    if not master or not follower:
        raise HTTPException(status_code=400, detail="Master and follower accounts are required.")
    if master == follower:
        raise HTTPException(status_code=400, detail="Master and follower accounts must be different.")
    state = read_state()
    logins = {int(x.get("login", 0)) for x in state.get("profiles", [])}
    if master not in logins or follower not in logins:
        raise HTTPException(status_code=400, detail="Both MT5 account profiles must exist before creating a copy relationship.")
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": f"copy-{uuid.uuid4().hex[:12]}",
        "name": str(payload.get("name") or f"{master} → {follower}"),
        "master_login": master,
        "follower_login": follower,
        "enabled": bool(payload.get("enabled", False)),
        "status": "stopped",  # real execution remains locked in this bridge
        "copy_mode": str(payload.get("copy_mode") or "balance_ratio"),
        "fixed_lot": float(payload.get("fixed_lot") or 0.01),
        "multiplier": float(payload.get("multiplier") or 1.0),
        "max_lot": float(payload.get("max_lot") or 1.0),
        "max_daily_loss": float(payload.get("max_daily_loss") or 100.0),
        "max_drawdown_pct": float(payload.get("max_drawdown_pct") or 5.0),
        "max_open_positions": int(payload.get("max_open_positions") or 3),
        "copy_new_trades": bool(payload.get("copy_new_trades", True)),
        "copy_sl_tp": bool(payload.get("copy_sl_tp", True)),
        "copy_closes": bool(payload.get("copy_closes", True)),
        "created_at": now,
        "last_event": "Saved — real copy worker not installed",
    }
    def mut(st):
        st.setdefault("copy_relationships", []).insert(0, row)
        st.setdefault("copy_events", []).insert(0, {
            "id": f"evt-{uuid.uuid4().hex[:12]}", "relationship_id": row["id"], "time": now,
            "action": "status", "message": "Copy relationship saved. Real execution is locked until isolated workers are available."
        })
        return row
    return update_state(mut)


@app.put("/api/mt5/copy/{relationship_id}")
def update_copy(relationship_id: str, payload: dict[str, Any] = Body(...)):
    def mut(st):
        row = next((x for x in st.get("copy_relationships", []) if str(x.get("id")) == relationship_id), None)
        if row is None:
            raise KeyError
        safe = {k: v for k, v in payload.items() if k not in {"id", "created_at"}}
        row.update(safe)
        # Do not report 'armed' in real bridge mode until the multi-terminal copy executor exists.
        if row.get("enabled"):
            row["status"] = "blocked"
            row["last_event"] = "Real copy worker required"
        else:
            row["status"] = "stopped"
        st.setdefault("copy_events", []).insert(0, {
            "id": f"evt-{uuid.uuid4().hex[:12]}", "relationship_id": relationship_id,
            "time": datetime.now(timezone.utc).isoformat(), "action": "status",
            "message": "Copy settings updated. Real execution remains safety-locked." if row.get("enabled") else "Copy relationship stopped."
        })
        st["copy_events"] = st["copy_events"][:500]
        return row
    try:
        return update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Copy relationship not found.")


@app.delete("/api/mt5/copy/{relationship_id}")
def delete_copy(relationship_id: str):
    def mut(st):
        before = len(st.get("copy_relationships", []))
        st["copy_relationships"] = [x for x in st.get("copy_relationships", []) if str(x.get("id")) != relationship_id]
        return len(st["copy_relationships"]) != before
    return {"ok": bool(update_state(mut))}


def _aggregate_ea_assignments(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    active = [row for row in rows if row.get("status") in {"starting", "running", "stopping"}]
    primary = dict((active or rows)[0])
    symbols = list(dict.fromkeys(str(row.get("symbol") or "") for row in rows if row.get("symbol")))
    trades = sum(int(row.get("bot_trade_count") or 0) for row in rows)
    wins = sum(int(row.get("bot_wins") or 0) for row in rows)
    losses = sum(int(row.get("bot_losses") or 0) for row in rows)
    statuses = {str(row.get("status") or "") for row in rows}
    if active:
        status = "running" if any(row.get("status") == "running" for row in active) else "starting"
    elif "paused" in statuses:
        status = "paused"
    elif "error" in statuses:
        status = "error"
    else:
        status = "stopped"
    last_trade = max(
        (row.get("last_trade") for row in rows if isinstance(row.get("last_trade"), dict)),
        key=lambda row: str(row.get("time") or ""),
        default=None,
    )
    primary.update({
        "status": status,
        "instances": rows,
        "ea_instances": rows,
        "symbols": symbols,
        "market_mode": "multi" if len(symbols) > 1 else "single",
        "instance_count": len(rows),
        "active_instance_count": len(active),
        "open_positions": sum(int(row.get("open_positions") or 0) for row in rows),
        "current_pl": sum(float(row.get("current_pl") or 0) for row in rows),
        "today_pl": sum(float(row.get("today_pl") or 0) for row in rows),
        "bot_trade_count": trades,
        "bot_wins": wins,
        "bot_losses": losses,
        "bot_win_rate": round(wins / trades * 100, 1) if trades else 0.0,
        "last_trade": last_trade,
        "ea_verified": bool(rows) and all(bool(row.get("ea_verified")) for row in active or rows),
        "account_verified": bool(rows) and all(bool(row.get("account_verified")) for row in active or rows),
        "terminal_status": "online" if active else "offline",
    })
    return primary


@app.get("/api/mt5/bots")
def bots():
    state = read_state()
    worker_status = ea_worker_client.status()
    if worker_status["status"] == "online":
        try:
            assignment_rows: dict[int, list[dict[str, Any]]] = {}
            for item in ea_worker_client.request("/bots"):
                assignment_rows.setdefault(int(item["bot_id"]), []).append(item)
            assignments = {bot_id: _aggregate_ea_assignments(rows) for bot_id, rows in assignment_rows.items()}
            def sync(st):
                for bot in st.get("bots", []):
                    if bot.get("native_engine"):
                        continue
                    assignment = assignments.get(int(bot.get("id", 0)))
                    if assignment:
                        assignment_active = assignment.get("status") in {"starting", "running", "stopping"}
                        bot.update({
                            "status": assignment["status"], "started_at": assignment.get("started_at") if assignment_active else None,
                            "worker_id": assignment.get("worker_id"), "terminal_id": assignment.get("terminal_id"),
                            "process_id": assignment.get("process_id") if assignment_active else None, "terminal_status": assignment.get("terminal_status"),
                            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
                            "account_verified": assignment.get("account_verified", False) if assignment_active else False,
                            "open_positions": assignment.get("open_positions", 0),
                            "current_pl": assignment.get("current_pl", 0), "today_pl": assignment.get("today_pl", 0),
                            "profit_today": assignment.get("today_pl", 0),
                            "account_open_positions": assignment.get("account_open_positions", 0),
                            "account_current_pl": assignment.get("account_current_pl", 0),
                            "metrics_scope": assignment.get("metrics_scope"),
                            "bot_trade_count": assignment.get("bot_trade_count", 0),
                            "bot_wins": assignment.get("bot_wins", 0), "bot_losses": assignment.get("bot_losses", 0),
                            "bot_win_rate": assignment.get("bot_win_rate", 0),
                            "detected_magic": assignment.get("detected_magic"),
                            "attribution_status": assignment.get("attribution_status", "pending"),
                            "last_trade": assignment.get("last_trade"), "metrics_error": assignment.get("metrics_error"),
                            "ea_verified": assignment.get("ea_verified", False) if assignment_active else False, "ea_status": assignment.get("ea_status"),
                            "verification_message": assignment.get("verification_message"),
                            "strategy_analysis": assignment.get("strategy_analysis"),
                            "background_mode": assignment.get("background_mode", False),
                            "symbols": assignment.get("symbols") or [assignment.get("symbol")],
                            "market_mode": assignment.get("market_mode", "single"),
                            "ea_instances": assignment.get("ea_instances") or assignment.get("instances") or [],
                            "instance_count": assignment.get("instance_count", 1),
                            "active_instance_count": assignment.get("active_instance_count", 1 if assignment_active else 0),
                        })
                    elif bot.get("status") in {"running", "connecting", "worker_offline"}:
                        bot["status"] = "stopped"
                        bot["started_at"] = None
                return st.get("bots", [])
            synced = update_state(sync)
            return _visible_bots_for_current_user(_overlay_bot_activity([dict(bot) for bot in synced]))
        except RuntimeError:
            pass
    elif any(bot.get("status") in {"running", "connecting"} for bot in state.get("bots", [])):
        def offline(st):
            for bot in st.get("bots", []):
                if bot.get("native_engine"):
                    continue
                if bot.get("status") in {"running", "connecting"}:
                    bot["status"] = "worker_offline"
            return st.get("bots", [])
        offline_rows = update_state(offline)
        return _visible_bots_for_current_user(_overlay_bot_activity([dict(bot) for bot in offline_rows]))
    return _visible_bots_for_current_user(_overlay_bot_activity([dict(bot) for bot in state.get("bots", [])]))


@app.post("/api/mt5/bots")
def create_bot(payload: dict[str, Any] = Body(...)):
    def mut(state):
        bots = state.setdefault("bots", [])
        next_id = max([int(x.get("id", 0)) for x in bots] + [1999]) + 1
        name = str(payload.get("name") or f"Custom EA {next_id}").strip()
        row = {
            "id": next_id, "name": name, "description": "Custom EA metadata.", "strategy": "Custom EA",
            "symbol": str(payload.get("symbol") or "EURUSD"), "timeframe": str(payload.get("timeframe") or "M15"),
            "recommended_timeframe": payload.get("recommended_timeframe"), "account_login": None, "status": "stopped",
            "lot_size": float(payload.get("lot_size") or 0.01), "win_rate": 0, "total_trades": 0, "net_profit": 0,
            "profit_today": 0, "version": str(payload.get("version") or "1.0.0"), "started_at": None,
            "ea_filename": payload.get("ea_filename"), "preset_filename": payload.get("preset_filename"),
            "file_status": "metadata-only", "upload_date": payload.get("upload_date"), "dll_required": bool(payload.get("dll_required", False)),
            "settings": payload.get("settings") or {"risk_percent": 1, "max_spread": 3.5, "trailing_stop": True, "magic_number": 510000 + next_id, "max_daily_loss": 250},
        }
        bots.append(row)
        return row
    return update_state(mut)




@app.post("/api/mt5/bots/{bot_id}/files")
async def upload_bot_files(
    bot_id: int,
    ea_file: UploadFile | None = File(default=None),
    preset_file: UploadFile | None = File(default=None),
):
    if ea_file is None and preset_file is None:
        raise HTTPException(status_code=400, detail="Choose an .ex5 EA file or .set preset to upload.")
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("system_preset"):
        raise HTTPException(status_code=403, detail="KOOLKID system preset files cannot be replaced by users.")

    bot_dir = EA_LIBRARY / current_workspace() / str(bot_id)
    result: dict[str, Any] = {"bot_id": bot_id}
    if ea_file is not None:
        result["ea"] = await _save_upload(ea_file, bot_dir, ".ex5")
    if preset_file is not None:
        result["preset"] = await _save_upload(preset_file, bot_dir, ".set")

    now = datetime.now(timezone.utc).isoformat()
    def mut(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if row is None:
            raise KeyError
        if "ea" in result:
            row["ea_filename"] = result["ea"]["filename"]
            row["ea_original_filename"] = result["ea"]["original_filename"]
            row["ea_stored_filename"] = result["ea"]["stored_filename"]
            row["ea_storage_path"] = result["ea"]["stored_path"]
            row["ea_size_bytes"] = result["ea"]["size_bytes"]
            row["ea_sha256"] = result["ea"]["sha256"]
            row["file_status"] = "ready"
            row["worker_compatibility"] = "ready"
            row["file_analysis"] = result["ea"].get("analysis")
        if "preset" in result:
            row["preset_filename"] = result["preset"]["filename"]
            row["preset_storage_path"] = result["preset"]["stored_path"]
            row["preset_size_bytes"] = result["preset"]["size_bytes"]
            row["preset_sha256"] = result["preset"]["sha256"]
            row["preset_analysis"] = result["preset"].get("analysis")
        row["upload_date"] = now
        row["library_revision"] = bot_library_revision(row)
        return dict(row)
    try:
        result["bot"] = update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _schedule_library_update_reconcile(current_workspace())
    return result


@app.post("/api/mt5/bots/{bot_id}/compile")
async def compile_bot_source(bot_id: int, source_file: UploadFile = File(...)):
    filename = _safe_upload_name(source_file.filename or "", ".mq5")
    data = await source_file.read(MAX_MQ5_FILE_BYTES + 1)
    if len(data) > MAX_MQ5_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"{filename} exceeds the 5 MB MQ5 source limit.")
    if not data:
        raise HTTPException(status_code=400, detail=f"{filename} is empty.")

    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("system_preset"):
        raise HTTPException(status_code=403, detail="KOOLKID system presets cannot be replaced by users.")

    bot_dir = EA_LIBRARY / current_workspace() / str(bot_id)
    try:
        compiled = await asyncio.to_thread(mq5_compiler.compile_mq5, data, filename, bot_dir)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    now = datetime.now(timezone.utc).isoformat()
    source_path = bot_dir / filename
    result = {k: v for k, v in compiled.items() if k != "ex5_path"}
    result["bot_id"] = bot_id

    def mut(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if row is None:
            raise KeyError
        row["source_filename"] = filename
        row["source_storage_path"] = str(source_path.relative_to(ROOT))
        row["source_sha256"] = hashlib.sha256(data).hexdigest()
        row["compile_status"] = "success" if compiled["success"] else "failed"
        row["compile_errors"] = int(compiled.get("errors") or 0)
        row["compile_warnings"] = int(compiled.get("warnings") or 0)
        row["compile_log"] = str(compiled.get("log") or "")[-12000:]
        row["compile_date"] = now
        row["upload_date"] = now
        if compiled["success"]:
            ex5_path = Path(str(compiled["ex5_path"]))
            ex5_data = ex5_path.read_bytes()
            row["ea_filename"] = ex5_path.name
            row["ea_storage_path"] = str(ex5_path.relative_to(ROOT))
            row["ea_size_bytes"] = len(ex5_data)
            row["ea_sha256"] = hashlib.sha256(ex5_data).hexdigest()
            row["file_status"] = "ready"
            row["worker_compatibility"] = "ready"
            row["file_analysis"] = {
                "format": "MT5 EX5", "compiled": True, "file_verified": True,
                "compiled_from_mq5": filename,
                "strategy_visibility": "Source was compiled server-side; EX5 is not decoded or reverse engineered.",
            }
        else:
            # A failed source update must not destroy an already working EX5.
            # New bots without a compiled artifact are marked compile-error.
            if not row.get("ea_storage_path"):
                row["file_status"] = "compile-error"
                row["worker_compatibility"] = "compile-error"
        row["library_revision"] = bot_library_revision(row)
        return dict(row)

    try:
        result["bot"] = update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _schedule_library_update_reconcile(current_workspace())
    return result


@app.get("/api/mt5/bots/{bot_id}/download")
def download_bot_ex5(bot_id: int):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("system_preset"):
        raise HTTPException(status_code=403, detail="KOOLKID system preset files are not available through user downloads.")

    filename = Path(str(bot.get("ea_filename") or "")).name
    if not filename.lower().endswith(".ex5"):
        raise HTTPException(status_code=404, detail="This bot does not have a compiled EX5 file.")

    bot_dir = (EA_LIBRARY / current_workspace() / str(bot_id)).resolve()
    ex5_path = (bot_dir / filename).resolve()
    if ex5_path.parent != bot_dir or not ex5_path.is_file():
        raise HTTPException(status_code=404, detail="The compiled EX5 file is not available.")

    return FileResponse(
        path=ex5_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@app.put("/api/mt5/bots/{bot_id}")
def update_bot(bot_id: int, payload: dict[str, Any] = Body(...)):
    current = next((b for b in read_state().get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(current)
    def mut(state):
        for i, bot in enumerate(state.get("bots", [])):
            if int(bot.get("id", 0)) == bot_id:
                if bot.get("system_preset"):
                    allowed = {"account_login", "symbol", "symbols", "market_mode", "timeframe", "bias_timeframe", "lot_size", "settings"}
                    safe = {k: v for k, v in payload.items() if k in allowed}
                else:
                    safe = {k: v for k, v in payload.items() if k not in {"id", "status", "started_at"}}
                state["bots"][i] = {**bot, **safe}
                revision = bot_library_revision(state["bots"][i])
                if revision:
                    state["bots"][i]["library_revision"] = revision
                return state["bots"][i]
        raise KeyError
    try:
        result = update_state(mut)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _schedule_library_update_reconcile(current_workspace())
    return result


@app.delete("/api/mt5/bots/{bot_id}")
def delete_bot(bot_id: int):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if bot and bot.get("system_preset"):
        raise HTTPException(status_code=403, detail="KOOLKID system presets cannot be deleted.")
    def mut(state):
        before = len(state.get("bots", []))
        state["bots"] = [b for b in state.get("bots", []) if int(b.get("id", 0)) != bot_id]
        return len(state["bots"]) != before
    return {"ok": bool(update_state(mut))}


@app.post("/api/mt5/bots/{bot_id}/start")
def start_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    login = int(payload.get("account_login") or bot.get("account_login") or 0)
    profile = next((p for p in state.get("profiles", []) if int(p.get("login", 0)) == login), None)
    if not profile:
        raise HTTPException(status_code=409, detail="Selected MT5 account profile was not found.")
    try:
        session = multi_account_client.worker_for_login(login)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    info = session.get("account_info") or {}
    raw_symbols = payload.get("symbols") or bot.get("symbols") or [payload.get("symbol") or bot.get("symbol")]
    if isinstance(raw_symbols, str):
        raw_symbols = [raw_symbols]
    symbols: list[str] = []
    for item in raw_symbols or []:
        value = str(item or "").strip()
        if value and value not in symbols:
            symbols.append(value)
    if not symbols:
        raise HTTPException(status_code=422, detail="Choose at least one market.")
    if len(symbols) > 10:
        raise HTTPException(status_code=422, detail="Choose no more than 10 markets for one bot.")
    symbol = symbols[0]
    available = {row["symbol"] for row in normalize_http_errors(lambda: multi_account_client.account_request(login, "/symbols?visible_only=false&limit=5000", timeout=15))}
    missing = [item for item in symbols if item not in available]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unavailable on the selected MT5 account: {', '.join(missing)}")

    if bot.get("native_engine") and not _is_black_rock_bot(bot):
        if not bot.get("native_ready"):
            raise HTTPException(status_code=409, detail=f"{bot.get('name') or 'This preset'} needs its MQ5 source before native execution can be enabled.")
        native_meta = dict(NATIVE_PRESETS.get(int(bot_id)) or {})
        execution_timeframe = str(payload.get("timeframe") or bot.get("timeframe") or native_meta.get("entry_tf") or "M5").upper()
        default_bias = str(native_meta.get("bias_tf") or "H1").replace("+", " ").split()[0]
        bias_timeframe = str(payload.get("bias_timeframe") or bot.get("bias_timeframe") or default_bias).upper()
        def save_native_config(st):
            row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
            if isinstance(payload.get("settings"), dict):
                row["settings"] = {**dict(row.get("settings") or {}), **dict(payload["settings"])}
            row.update({
                "account_login": login, "symbol": symbol, "symbols": symbols,
                "market_mode": "multi" if len(symbols) > 1 else "single",
                "timeframe": execution_timeframe, "bias_timeframe": bias_timeframe,
                "lot_size": float(payload.get("lot_size") or row.get("lot_size") or 0.01),
            })
            return dict(row)
        update_state(save_native_config)
        try:
            result = native_runtime.start(
                current_workspace(), bot_id, login, symbol,
                symbols=symbols,
                allow_live=bool(payload.get("confirm_live")),
                scan_seconds=int(payload.get("scan_seconds") or 20),
                execution_timeframe=execution_timeframe,
                bias_timeframe=bias_timeframe,
            )
            revision = str(bot.get("library_revision") or bot_library_revision(bot) or "")
            if revision:
                _mark_library_revision_running(bot_id, revision)
            return result
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    ea_rel = bot.get("ea_storage_path")
    if _is_black_rock_bot(bot):
        bundled_black_rock = ROOT / "data" / "system_ea_library" / "Black_Rock.ex5"
        if bundled_black_rock.is_file():
            ea_rel = str(bundled_black_rock.relative_to(ROOT))
    if not ea_rel or not (ROOT / ea_rel).is_file():
        if _is_black_rock_bot(bot):
            raise HTTPException(status_code=409, detail="BLACK ROCK compiled EA is unavailable on this server.")
        raise HTTPException(status_code=409, detail="Uploaded .ex5 file was not found. Upload the EA before starting it.")
    preset_rel = bot.get("preset_storage_path")
    worker_payload = {
        "bot_id": bot_id, "account_login": login, "account_type": "live" if int(info.get("trade_mode") or 0) == 2 else "demo",
        "server": profile.get("server"), "symbol": symbol, "timeframe": str(payload.get("timeframe") or bot.get("timeframe") or ""),
        "ea_path": str((ROOT / ea_rel).resolve()), "ea_filename": bot.get("ea_filename"),
        "preset_path": str((ROOT / preset_rel).resolve()) if preset_rel else None, "preset_filename": bot.get("preset_filename"),
        "terminal_path": payload.get("terminal_path"), "allow_live": bool(payload.get("confirm_live")),
        "bridge_terminal_path": info.get("terminal_path"), "bridge_data_path": info.get("data_path"),
        "allow_dll": bool(payload.get("allow_dll")), "dll_required": bool(bot.get("dll_required")),
        "configured_magic": int((bot.get("settings") or {}).get("magic_number") or 0) or None,
    }
    def mark_starting(st):
        row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
        row.update({
            **{k: v for k, v in payload.items() if k in {"account_login", "timeframe", "lot_size", "settings"}},
            "symbol": symbol,
            "symbols": symbols,
            "market_mode": "multi" if len(symbols) > 1 else "single",
            "status": "connecting",
        })
        return row
    update_state(mark_starting)
    started_assignments: list[dict[str, Any]] = []
    try:
        for index, market_symbol in enumerate(symbols, start=1):
            instance_payload = {
                **worker_payload,
                "symbol": market_symbol,
                "instance_key": f"market-{index}",
            }
            started_assignments.append(
                ea_worker_client.request("/bots/start", "POST", instance_payload, timeout=120)
            )
        assignment = _aggregate_ea_assignments(started_assignments)
    except RuntimeError as exc:
        for started in started_assignments:
            instance_key = str(started.get("instance_key") or "")
            if not instance_key:
                continue
            try:
                ea_worker_client.request(
                    f"/bots/{bot_id}/instances/{quote(instance_key)}/stop",
                    "POST", {}, timeout=15,
                )
            except RuntimeError:
                pass
        def mark_error(st):
            row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
            row.update({"status": "error", "last_error": str(exc), "ea_instances": started_assignments})
            return row
        update_state(mark_error)
        raise HTTPException(status_code=409, detail=str(exc))
    def mark_running(st):
        row = next(b for b in st["bots"] if int(b["id"]) == bot_id)
        row.update({
            "status": assignment["status"], "started_at": assignment.get("started_at"),
            "session_started_at": assignment.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "worker_id": assignment.get("worker_id"), "terminal_id": assignment.get("terminal_id"),
            "process_id": assignment.get("process_id"), "terminal_status": assignment.get("terminal_status"),
            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
            "account_verified": assignment.get("account_verified", False),
            "open_positions": assignment.get("open_positions", 0),
            "current_pl": assignment.get("current_pl", 0), "today_pl": 0,
            "profit_today": 0,
            "account_open_positions": assignment.get("account_open_positions", 0),
            "account_current_pl": assignment.get("account_current_pl", 0),
            "metrics_scope": "Current bot session · verified attributed activity.",
            "bot_trade_count": 0,
            "bot_wins": 0, "bot_losses": 0,
            "bot_win_rate": 0,
            "detected_magic": assignment.get("detected_magic"),
            "attribution_status": assignment.get("attribution_status", "pending"),
            "last_trade": None, "metrics_error": assignment.get("metrics_error"),
            "ea_verified": assignment.get("ea_verified", False), "ea_status": assignment.get("ea_status"),
            "verification_message": assignment.get("verification_message"),
            "strategy_analysis": assignment.get("strategy_analysis"),
            "background_mode": assignment.get("background_mode", False),
            "symbols": symbols,
            "market_mode": "multi" if len(symbols) > 1 else "single",
            "ea_instances": assignment.get("ea_instances") or assignment.get("instances") or started_assignments,
            "instance_count": len(started_assignments),
            "active_instance_count": len([item for item in started_assignments if item.get("status") in {"starting", "running"}]),
            "running_library_revision": str(bot.get("library_revision") or bot_library_revision(bot) or "") or row.get("running_library_revision"),
            "library_update_error": None,
        })
        return row
    return update_state(mark_running)


@app.post("/api/mt5/bots/{bot_id}/pause")
def pause_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("native_engine") and not _is_black_rock_bot(bot):
        try:
            return native_runtime.pause(current_workspace(), bot_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    try:
        assignment = ea_worker_client.request(f"/bots/{bot_id}/pause", "POST", {}, timeout=20)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    def mark_paused(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if not row:
            raise KeyError
        row.update({
            "status": "paused",
            "process_id": None,
            "terminal_status": "offline",
            "ea_status": "paused",
            "paused_at": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
            "ea_instances": assignment.get("instances") or [],
            "active_instance_count": 0,
        })
        return row

    try:
        return update_state(mark_paused)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")


@app.post("/api/mt5/bots/{bot_id}/resume")
def resume_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("native_engine") and not _is_black_rock_bot(bot):
        try:
            return native_runtime.resume(current_workspace(), bot_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    try:
        assignment = ea_worker_client.request(f"/bots/{bot_id}/resume", "POST", {}, timeout=75)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    instances = assignment.get("instances") or [assignment]
    aggregate = _aggregate_ea_assignments([dict(item) for item in instances if isinstance(item, dict)])

    def mark_resumed(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if not row:
            raise KeyError
        row.update({
            "status": aggregate.get("status") or assignment.get("status") or "running",
            "started_at": row.get("started_at") or aggregate.get("started_at") or assignment.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "session_started_at": row.get("session_started_at") or row.get("started_at") or aggregate.get("started_at") or assignment.get("started_at") or datetime.now(timezone.utc).isoformat(),
            "process_id": aggregate.get("process_id") or assignment.get("process_id"),
            "terminal_status": aggregate.get("terminal_status") or assignment.get("terminal_status") or "online",
            "ea_status": aggregate.get("ea_status") or assignment.get("ea_status") or "active",
            "ea_verified": aggregate.get("ea_verified", assignment.get("ea_verified", False)),
            "account_verified": aggregate.get("account_verified", assignment.get("account_verified", False)),
            "last_activity": aggregate.get("last_activity") or assignment.get("last_activity"),
            "last_error": aggregate.get("error") or assignment.get("error"),
            "ea_instances": instances,
            "active_instance_count": len([item for item in instances if item.get("status") in {"starting", "running"}]),
        })
        return row

    try:
        return update_state(mark_resumed)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")


@app.post("/api/mt5/bots/{bot_id}/stop")
def stop_bot(bot_id: int, payload: dict[str, Any] = Body(default_factory=dict)):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    if bot.get("native_engine") and not _is_black_rock_bot(bot):
        try:
            return native_runtime.stop(current_workspace(), bot_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    try:
        assignment = ea_worker_client.request(f"/bots/{bot_id}/stop", "POST", {}, timeout=15)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    def mark_stopped(st):
        row = next((b for b in st.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
        if not row:
            raise KeyError
        row.update({
            "status": assignment.get("status", "stopped"), "started_at": None, "session_started_at": None, "process_id": None,
            "terminal_status": assignment.get("terminal_status", "offline"), "account_verified": False,
            "last_activity": assignment.get("last_activity"), "last_error": assignment.get("error"),
            "ea_verified": False, "ea_status": "stopped",
            "ea_instances": assignment.get("instances") or [],
            "active_instance_count": 0,
        })
        return row
    try:
        return update_state(mark_stopped)
    except KeyError:
        raise HTTPException(status_code=404, detail="Bot not found.")


@app.get("/api/mt5/bots/{bot_id}/performance")
def bot_performance(bot_id: int):
    state = read_state()
    bot = next((b for b in state.get("bots", []) if int(b.get("id", 0)) == bot_id), None)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found.")
    _require_black_rock_lifetime_access(bot)
    rows = history(30)
    if bot.get("native_engine") and not _is_black_rock_bot(bot):
        prefix = f"KKN{int(bot_id)}"
        tagged = [r for r in rows if str(r.get("source", "")).startswith(prefix)]
    else:
        tagged = [r for r in rows if str(r.get("source", "")).upper() == str(bot.get("name", "")).upper()]
    pnl = [float(r["profit"]) + float(r["swap"]) + float(r["commission"]) for r in tagged]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    curve = peak = max_dd = 0.0
    for value in reversed(pnl):
        curve += value
        peak = max(peak, curve)
        max_dd = max(max_dd, peak - curve)
    return {
        "bot_id": bot_id, "trades": len(pnl), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(pnl) * 100, 1) if pnl else 0,
        "gross_profit": round(sum(wins), 2), "gross_loss": round(sum(losses), 2), "net_pl": round(sum(pnl), 2),
        "average_win": round(sum(wins) / len(wins), 2) if wins else 0, "average_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "largest_win": max(wins) if wins else 0, "largest_loss": min(losses) if losses else 0,
        "current_drawdown": round(max(0, peak - curve), 2), "max_drawdown": round(max_dd, 2),
    }


@app.post("/api/mt5/emergency/stop-all-bots")
def emergency_stop_bots():
    try:
        for assignment in ea_worker_client.request("/bots/running", timeout=5):
            try:
                ea_worker_client.request(f"/bots/{int(assignment['bot_id'])}/stop", "POST", {}, timeout=15)
            except RuntimeError:
                pass
    except RuntimeError:
        pass
    def mut(state):
        stopped = 0
        for b in state.get("bots", []):
            if b.get("status") in {"running", "paused", "connecting"}:
                b["status"] = "stopped"
                b["started_at"] = None
                b["process_id"] = None
                b["terminal_status"] = "offline"
                b["account_verified"] = False
                stopped += 1
        return stopped
    return {"ok": True, "stopped": int(update_state(mut))}


@app.post("/api/mt5/emergency/stop-and-close-all")
def emergency_stop_close():
    stopped = emergency_stop_bots()["stopped"]
    result = close_all_positions()
    return {"ok": True, "stopped": stopped, "closed": result["closed"], "realized": result["realized"]}


@app.get("/api/mt5/ai/trial")
def get_ai_trial():
    snapshot = load_ai_trial_snapshot()
    if snapshot:
        snapshot = dict(snapshot)
        snapshot["execution_lock"] = "live_requires_explicit_confirmation"
    scan_config = dict(read_state().get("ai_scan_config") or {})
    if not scan_config and snapshot:
        scan_config = {
            "account_login": int(snapshot.get("account_login") or 0),
            "symbol": str(snapshot.get("symbol") or ""),
            "execution_timeframe": str(snapshot.get("execution_timeframe") or "M15"),
            "bias_timeframe": str(snapshot.get("bias_timeframe") or "H4"),
        }
    exec_tf = str(scan_config.get("execution_timeframe") or (snapshot or {}).get("execution_timeframe") or "M15")
    bias_tf = str(scan_config.get("bias_timeframe") or (snapshot or {}).get("bias_timeframe") or "H4")
    return {
        "trial_version": "1.0-user-trial",
        "strategy": "Human Apostle",
        "mode": "EXECUTION_REQUIRES_LIVE_CONFIRMATION",
        "execution_timeframe": exec_tf,
        "bias_timeframe": bias_tf,
        "snapshot": snapshot,
        "scan_config": scan_config,
        "execution": "Human Apostle can scan manually or run continuously on the server. Live execution requires explicit confirmation for the selected account.",
    }


@app.post("/api/mt5/ai/trial/scan")
def scan_ai_trial(payload: AiTrialScanPayload):
    try:
        result = _run_ai_trial_scan(payload)
        def save_scan_config(state):
            state["ai_scan_config"] = {
                "account_login": payload.account_login,
                "symbol": payload.symbol,
                "execution_timeframe": str(payload.execution_timeframe),
                "bias_timeframe": str(payload.bias_timeframe),
            }
            return state["ai_scan_config"]
        update_state(save_scan_config)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        session_error(exc)


@app.post("/api/mt5/ai/trial/execute")
def execute_ai_trial(payload: AiTrialExecutePayload):
    snapshot = load_ai_trial_snapshot()
    if not snapshot:
        raise HTTPException(status_code=404, detail="No Apostle snapshot exists yet. Run a scan first.")
    if int(snapshot.get("account_login") or 0) != int(payload.account_login) or str(snapshot.get("symbol") or "") != payload.symbol:
        raise HTTPException(status_code=409, detail="The stored Apostle snapshot no longer matches the selected account and symbol. Run a fresh scan first.")
    try:
        execution = _execute_apostle_snapshot(
            snapshot,
            payload.volume,
            source="ai_manual_human_apostle",
            allow_live=bool(payload.confirm_live),
        )
        _ai_event("manual_ai_trade_executed", symbol=payload.symbol, direction=execution.get("direction"), signal_time=execution.get("signal_time"), volume=payload.volume)
        return execution
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        session_error(exc)


@app.delete("/api/mt5/ai/trial")
def delete_ai_trial():
    clear_ai_trial_snapshot()
    return {"ok": True}


@app.get("/api/mt5/ai/auto-select")
def get_ai_auto_select():
    return ai_auto_select.status(current_workspace())


@app.post("/api/mt5/ai/auto-select/scan")
def scan_ai_auto_select(payload: AiAutoSelectScanPayload):
    try:
        return ai_auto_select.scan_and_store(payload.account_login, payload.symbol, payload.enabled_bot_ids or None)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        session_error(exc)


@app.put("/api/mt5/ai/auto-select")
def configure_ai_auto_select(payload: AiAutoSelectConfigPayload):
    try:
        return ai_auto_select.configure(current_workspace(), payload.model_dump())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        session_error(exc)


@app.post("/api/mt5/ai/auto-select/execute")
def execute_ai_auto_select(payload: AiAutoSelectExecutePayload):
    try:
        return ai_auto_select.manual_execute(confirm_live=bool(payload.confirm_live))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/mt5/ai/auto")
def get_ai_auto():
    return _ai_auto_status()


@app.put("/api/mt5/ai/auto")
def configure_ai_auto(payload: AiAutoConfigPayload):
    workspace_id = current_workspace()
    if payload.enabled:
        if not payload.account_login or not payload.symbol or not payload.volume:
            raise HTTPException(status_code=422, detail="Choose a connected MT5 account, symbol, and fixed lot size before starting AI Auto-Trading.")
        auto_select_cfg = read_state().get("ai_auto_select_config") or {}
        if auto_select_cfg.get("enabled") and str(auto_select_cfg.get("mode") or "").lower() == "auto":
            raise HTTPException(status_code=409, detail="Stop Auto Select automatic execution before starting Human Apostle Auto-Trading.")
        try:
            _connected_ai_account(payload.account_login, allow_live=bool(payload.confirm_live))
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except RuntimeError as exc:
            session_error(exc)
        config = {
            "enabled": True,
            "strategy": "human_apostle",
            "account_login": int(payload.account_login),
            "symbol": str(payload.symbol).strip(),
            "volume": float(payload.volume),
            "scan_seconds": int(payload.scan_seconds),
            "execution_timeframe": str(payload.execution_timeframe),
            "bias_timeframe": str(payload.bias_timeframe),
            "allow_live": bool(payload.confirm_live),
            "updated_at": _ai_now(),
        }
        def enable(st):
            st["ai_auto_config"] = config
            st["ai_scan_config"] = {
                "account_login": config["account_login"],
                "symbol": config["symbol"],
                "execution_timeframe": config["execution_timeframe"],
                "bias_timeframe": config["bias_timeframe"],
            }
            settings = st.setdefault("ai_settings", {})
            settings["auto_trading"] = True
            runtime = st.setdefault("ai_auto_runtime", {})
            runtime.update({"status": "starting", "last_error": None})
            return config
        update_state(enable)
        _ai_event("auto_trading_started", account_login=config["account_login"], symbol=config["symbol"], volume=config["volume"])
        _start_ai_scanner(workspace_id)
    else:
        def disable(st):
            config = st.setdefault("ai_auto_config", {})
            config["enabled"] = False
            config["updated_at"] = _ai_now()
            st.setdefault("ai_settings", {})["auto_trading"] = False
            st.setdefault("ai_auto_runtime", {})["status"] = "stopping"
            return config
        update_state(disable)
        _ai_event("auto_trading_stopped")
        _stop_ai_scanner(workspace_id)
    return _ai_auto_status()


@app.get("/api/mt5/ai")
def get_ai():
    state = read_state()
    settings = state.get("ai_settings", {})
    insights = []
    live_accounts = [row for row in accounts() if row.get("status") == "connected"]
    now = datetime.now(timezone.utc).isoformat()
    if live_accounts:
        try:
            k = stats()["kpis"]
            sentiment = "critical" if k["drawdown_pct"] >= 8 else "warning" if k["drawdown_pct"] >= 4 else "neutral"
            insights.append({"id": 1, "title": "Live MT5 bridge status", "body": f"Account data is live. Equity {k['total_equity']:.2f}, floating P/L {k['floating']:.2f}, open positions {k['open_positions']}.", "category": "performance", "sentiment": sentiment, "confidence": 100, "account_login": None, "bot_id": None, "created_at": now})
        except Exception:
            pass
    else:
        insights.append({"id": 1, "title": "MT5 bridge waiting", "body": "Connect an MT5 account.", "category": "market", "sentiment": "warning", "confidence": 100, "account_login": None, "bot_id": None, "created_at": now})
    return {"insights": insights, "settings": settings}


@app.post("/api/mt5/ai")
def generate_ai():
    return get_ai()


@app.delete("/api/mt5/ai")
def delete_ai(payload: dict[str, Any] = Body(default_factory=dict)):
    return {"ok": True}


@app.put("/api/mt5/ai")
def save_ai(payload: dict[str, Any] = Body(...)):
    settings = payload.get("settings") or {}
    def mut(state):
        state["ai_settings"] = settings
        return settings
    result = update_state(mut)
    state = read_state()
    auto_config = state.get("ai_auto_config") or {}
    if not result.get("auto_trading") and auto_config.get("enabled"):
        def disable_auto(st):
            st.setdefault("ai_auto_config", {})["enabled"] = False
            st.setdefault("ai_auto_runtime", {})["status"] = "stopping"
            return st["ai_settings"]
        result = update_state(disable_auto)
        _stop_ai_scanner(current_workspace())
    elif result.get("auto_trading") and auto_config.get("enabled"):
        _start_ai_scanner(current_workspace())
    return result


# Deriv execution is deliberately not implemented by the MT5 bridge.
@app.get("/api/deriv/accounts")
def deriv_accounts():
    return []


@app.post("/api/deriv/accounts/{account_id}/active")
def deriv_active(account_id: int):
    raise HTTPException(status_code=501, detail="Deriv accounts remain in the separate Deriv integration path.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.getenv("MT5_BRIDGE_HOST", "127.0.0.1"), port=int(os.getenv("MT5_BRIDGE_PORT", "8000")))
