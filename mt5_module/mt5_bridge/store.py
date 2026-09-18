from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT.parent))
from hub_auth import current_workspace
from native_strategies.catalog import NATIVE_PRESETS
_LOCK = threading.RLock()


def _state_file() -> Path:
    return DATA_DIR / "workspaces" / current_workspace() / "bridge_state.json"

SYSTEM_BOT_PRESETS = [
    {"id": 1000, "name": "PRIMORDIAL BLACK", "file": "Primordial_Black.ex5", "version": "2.10", "magic": 26033177},
    {"id": 1001, "name": "PRIMORDIAL BLUE", "file": "Primordial_Blue.ex5", "version": "2.20", "magic": 26033177},
    {"id": 1002, "name": "PRIMORDIAL EMERALD", "file": "Primordial_Emerald.ex5", "version": "1.10", "magic": 26033178},
    {"id": 1003, "name": "PRIMORDIAL GOLD", "file": "Primordial_Gold.ex5", "version": "1.10", "magic": 26033177},
    {"id": 1004, "name": "PRIMORDIAL PURPLE", "file": "Primordial_Purple.ex5", "version": "1.00", "magic": 26033177},
    {"id": 1005, "name": "PRIMORDIAL RED", "file": "Primordial_Red.ex5", "version": "1.10", "magic": 26033178},
    {"id": 1006, "name": "PRIMORDIAL SILVER", "file": "Primordial_Silver.ex5", "version": "1.20", "magic": 90412026},
    {"id": 1007, "name": "PRIMORDIAL WHITE", "file": "Primordial_White.ex5", "version": "1.10", "magic": 26033179},
    {"id": 1008, "name": "BLACK ROCK", "file": "Black_Rock.ex5", "version": "1.0.0", "magic": 511008},
    {"id": 1009, "name": "DEAR BRUCE PREMIUM", "file": "DEAR_BRUCE_PREMIUM.ex5", "version": "1.0.0", "magic": 511009},
]


def _system_ea_library() -> Path:
    return DATA_DIR / "system_ea_library"


def _merge_system_bots(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {int(row.get("id", 0)): dict(row) for row in existing if isinstance(row, dict)}
    system_ids = {int(p["id"]) for p in SYSTEM_BOT_PRESETS}
    rows = [dict(row) for row in existing if int(row.get("id", 0)) not in system_ids]
    for preset in SYSTEM_BOT_PRESETS:
        bot_id = int(preset["id"])
        path = _system_ea_library() / str(preset["file"])
        legacy_ready = path.is_file()
        native = dict(NATIVE_PRESETS.get(bot_id) or {})
        native_ready = bool(native.get("ready"))
        canonical = {
            "id": bot_id, "name": preset["name"],
            "display_title": native.get("title") or "KOOLKID System Strategy",
            "display_subtitle": native.get("subtitle") or "Built-in KOOLKID trading strategy",
            "description": native.get("subtitle") or "KOOLKID built-in trading strategy.",
            "strategy": "System Preset", "symbol": "XAUUSD", "timeframe": native.get("entry_tf") or "M5",
            "account_login": None, "status": "stopped", "lot_size": 0.01,
            "win_rate": 0, "total_trades": 0, "net_profit": 0, "profit_today": 0,
            "version": preset["version"], "started_at": None,
            "ea_filename": preset["file"], "preset_filename": None,
            "file_status": "native" if native_ready else "source-required", "dll_required": False,
            "ea_storage_path": str(path.relative_to(ROOT)) if legacy_ready else None,
            "ea_size_bytes": path.stat().st_size if legacy_ready else None,
            "ea_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if legacy_ready else None,
            "legacy_ex5_available": legacy_ready,
            "system_preset": True, "locked": True,
            "native_engine": True, "native_key": native.get("key"),
            "native_ready": native_ready, "native_source": native.get("source"),
            "engine_type": "native" if native_ready else "source_required",
            "bias_timeframe": native.get("bias_tf"),
            "settings": {"risk_percent": 0.5, "max_spread": 3.5, "trailing_stop": True,
                         "magic_number": int(native.get("magic") or preset["magic"]), "max_daily_loss": 250, "max_open_positions": 3},
        }
        current = by_id.get(bot_id, {})
        row = {**canonical, **current}
        for key in (
            "id", "name", "display_title", "display_subtitle", "description", "strategy", "version",
            "ea_filename", "preset_filename", "file_status", "dll_required",
            "ea_storage_path", "ea_size_bytes", "ea_sha256", "legacy_ex5_available",
            "system_preset", "locked", "native_engine", "native_key", "native_ready",
            "native_source", "engine_type", "bias_timeframe",
        ):
            row[key] = canonical[key]
        current_settings = current.get("settings") if isinstance(current.get("settings"), dict) else {}
        row["settings"] = {**canonical["settings"], **current_settings}
        row["settings"]["magic_number"] = canonical["settings"]["magic_number"]
        rows.append(row)
    rows.sort(key=lambda row: (0 if row.get("system_preset") else 1, int(row.get("id", 0))))
    return rows


def default_risk() -> dict[str, Any]:
    return {
        "id": "global",
        "scope": "global",
        "account_login": None,
        "bot_id": None,
        "max_daily_loss": 500,
        "max_daily_profit": 1500,
        "max_drawdown_pct": 10,
        "max_lot_size": 5,
        "max_open_positions": 10,
        "max_trades_per_day": 100,
        "max_risk_per_trade": 2,
        "allowed_trading_hours": "00:00-23:59",
        "allowed_symbols": [],
        "auto_stop": True,
    }


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "profiles": [],
        "active_login": None,
        "bots": _merge_system_bots([]),
        "risk": [default_risk()],
        "ai_settings": {
            "auto_trading": False,
            "risk_guard": True,
            "sentiment_filter": False,
            "news_pause": True,
        },
        "copy_relationships": [],
        "copy_events": [],
    }


def _load_unlocked() -> dict[str, Any]:
    state_file = _state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if not state_file.exists():
        state = _default_state()
        _save_unlocked(state)
        return state
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError("unsupported state")
    except Exception:
        state = _default_state()
        _save_unlocked(state)
        return state

    bots = [x for x in state.get("bots", []) if isinstance(x, dict)]
    merged_bots = _merge_system_bots(bots)
    if merged_bots != bots:
        state["bots"] = merged_bots
        _save_unlocked(state)
    else:
        state["bots"] = bots
    state.setdefault("profiles", [])
    state.setdefault("active_login", None)
    state.setdefault("risk", [default_risk()])
    state.setdefault("ai_settings", _default_state()["ai_settings"])
    state.setdefault("copy_relationships", [])
    state.setdefault("copy_events", [])
    return state


def _save_unlocked(state: dict[str, Any]) -> None:
    state_file = _state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_name(
        f"{state_file.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    payload = json.dumps(state, indent=2)
    try:
        tmp.write_text(payload, encoding="utf-8")
        for attempt in range(8):
            try:
                os.replace(tmp, state_file)
                break
            except PermissionError:
                if attempt == 7:
                    # Windows tools can hold a read handle without FILE_SHARE_DELETE.
                    # Preserve the state update by writing in place rather than failing
                    # the whole API request just because the destination cannot be renamed.
                    with state_file.open("w", encoding="utf-8") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    break
                time.sleep(0.025 * (attempt + 1))
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def read_state() -> dict[str, Any]:
    with _LOCK:
        return deepcopy(_load_unlocked())


def update_state(mutator):
    with _LOCK:
        state = _load_unlocked()
        result = mutator(state)
        _save_unlocked(state)
        return deepcopy(result)


def upsert_profile(profile: dict[str, Any], make_active: bool = True) -> dict[str, Any]:
    login = int(profile["login"])

    def mut(state):
        rows = state["profiles"]
        idx = next((i for i, row in enumerate(rows) if int(row.get("login", 0)) == login), -1)
        if idx >= 0:
            prior = rows[idx]
            profile.setdefault("id", prior.get("id", idx + 1))
            rows[idx] = {**prior, **profile}
            row = rows[idx]
        else:
            profile.setdefault("id", max([int(r.get("id", 0)) for r in rows] + [0]) + 1)
            rows.append(profile)
            row = profile
        if make_active:
            state["active_login"] = login
            for item in rows:
                item["is_active"] = int(item.get("login", 0)) == login
        return row

    return update_state(mut)


def remove_profile(profile_id: int) -> bool:
    def mut(state):
        before = len(state["profiles"])
        removed_login = None
        for row in state["profiles"]:
            if int(row.get("id", 0)) == profile_id:
                removed_login = int(row.get("login", 0))
                break
        state["profiles"] = [r for r in state["profiles"] if int(r.get("id", 0)) != profile_id]
        if removed_login and state.get("active_login") == removed_login:
            state["active_login"] = None
        for bot in state["bots"]:
            if removed_login and bot.get("account_login") == removed_login:
                bot["account_login"] = None
                bot["status"] = "stopped"
        return len(state["profiles"]) != before

    return bool(update_state(mut))
