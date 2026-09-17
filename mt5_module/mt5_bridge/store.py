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
    return DATA_DIR / "workspaces" / current_workspace() / "bridge_state.json"

PREINSTALLED_BOT_NAMES = [
    "WASP",
    "PRIMORDIAL PURPLE",
    "PRIMORDIAL BLACK",
    "PRIMORDIAL RED",
    "PRIMORDIAL WHITE",
    "PRIMORDIAL SILVER",
    "PRIMORDIAL GOLD",
    "PRIMORDIAL EMERALD",
    "PRIMORDIAL BLUE",
    "JOHN WICK",
    "JAMAICA",
    "PUSH",
    "NICK",
    "RED RIOT",
    "SCARLET RAIN",
    "CRIMSON RIOT",
    "MAROON",
    "TLG",
    "BOOM",
    "CRASH",
]


def _is_preinstalled_placeholder(bot: dict[str, Any]) -> bool:
    try:
        bot_id = int(bot.get("id", 0))
    except (TypeError, ValueError):
        return False
    return (
        1000 <= bot_id < 1000 + len(PREINSTALLED_BOT_NAMES)
        and str(bot.get("name", "")).upper() in PREINSTALLED_BOT_NAMES
        and bot.get("file_status") != "ready"
        and not bot.get("ea_storage_path")
    )


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
        "bots": [],
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
    filtered_bots = [x for x in bots if not _is_preinstalled_placeholder(x)]
    if len(filtered_bots) != len(bots):
        state["bots"] = filtered_bots
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
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(state_file)


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
