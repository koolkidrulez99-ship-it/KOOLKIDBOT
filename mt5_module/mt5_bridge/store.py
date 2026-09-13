from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "bridge_state.json"
_LOCK = threading.RLock()

BOT_NAMES = [
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


def _default_bot(name: str, index: int) -> dict[str, Any]:
    symbol = "XAUUSD" if name in {"WASP", "NICK"} else "EURUSD"
    timeframe = "M1" if name == "WASP" else "M5" if name == "NICK" else "M15"
    return {
        "id": 1000 + index,
        "name": name,
        "description": "Custom EA. Strategy details remain neutral until the real EA package is attached.",
        "strategy": "Custom EA",
        "symbol": symbol,
        "timeframe": timeframe,
        "recommended_timeframe": timeframe if name in {"WASP", "NICK"} else None,
        "account_login": None,
        "status": "stopped",
        "lot_size": 0.01,
        "win_rate": 0,
        "total_trades": 0,
        "net_profit": 0,
        "profit_today": 0,
        "version": "1.0.0",
        "started_at": None,
        "ea_filename": name.replace(" ", "_") + ".ex5",
        "preset_filename": None,
        "file_status": "metadata-only",
        "upload_date": None,
        "dll_required": False,
        "settings": {
            "risk_percent": 1,
            "max_spread": 3.5,
            "trailing_stop": True,
            "magic_number": 510000 + index,
            "max_daily_loss": 250,
            "slippage": 1.5,
            "max_open_positions": 3,
            "trading_session": "All Sessions",
        },
    }


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
        "bots": [_default_bot(name, i) for i, name in enumerate(BOT_NAMES)],
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        state = _default_state()
        _save_unlocked(state)
        return state
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or state.get("version") != 1:
            raise ValueError("unsupported state")
    except Exception:
        state = _default_state()
        _save_unlocked(state)
        return state

    existing = {str(x.get("name", "")).upper(): x for x in state.get("bots", []) if isinstance(x, dict)}
    state["bots"] = [
        {**_default_bot(name, i), **existing.get(name.upper(), {})}
        for i, name in enumerate(BOT_NAMES)
    ] + [
        x for x in state.get("bots", [])
        if isinstance(x, dict) and str(x.get("name", "")).upper() not in {n.upper() for n in BOT_NAMES}
    ]
    state.setdefault("profiles", [])
    state.setdefault("active_login", None)
    state.setdefault("risk", [default_risk()])
    state.setdefault("ai_settings", _default_state()["ai_settings"])
    state.setdefault("copy_relationships", [])
    state.setdefault("copy_events", [])
    return state


def _save_unlocked(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


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
