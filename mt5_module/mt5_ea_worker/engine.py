from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception as exc:  # allows docs/tests to run on non-Windows systems
    mt5 = None
    MT5_IMPORT_ERROR = str(exc)
else:
    MT5_IMPORT_ERROR = None

from store import read_state, update_state, upsert_profile

_LOCK = threading.RLock()
_CONNECTED_LOGIN: int | None = None
_LAST_HEARTBEAT: str | None = None
_LAST_ERROR: str | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mt5_required():
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 Python package is not available. Run SETUP_MT5_BRIDGE.bat on Windows."
            + (f" Import error: {MT5_IMPORT_ERROR}" if MT5_IMPORT_ERROR else "")
        )
    return mt5


def last_error_text() -> str:
    if mt5 is None:
        return MT5_IMPORT_ERROR or "MetaTrader5 package unavailable"
    try:
        return str(mt5.last_error())
    except Exception:
        return "Unknown MT5 error"


def _terminal_path() -> str | None:
    raw = os.getenv("MT5_TERMINAL_PATH", "").strip().strip('"')
    if raw:
        return raw
    default = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "MetaTrader 5" / "terminal64.exe"
    return str(default.resolve()) if default.is_file() else None


def initialize_terminal(login: int | None = None, password: str | None = None, server: str | None = None) -> bool:
    global _LAST_ERROR
    module = _mt5_required()
    path = _terminal_path()
    timeout = max(5000, min(int(os.getenv("MT5_IPC_TIMEOUT_MS", "20000")), 120000))
    kwargs: dict[str, Any] = {"timeout": timeout}
    if login:
        kwargs["login"] = int(login)
    if password:
        kwargs["password"] = password
    if server:
        kwargs["server"] = server
    try:
        ok = module.initialize(path, **kwargs) if path else module.initialize(**kwargs)
    except Exception as exc:
        _LAST_ERROR = str(exc)
        return False
    if not ok:
        _LAST_ERROR = last_error_text()
    else:
        _LAST_ERROR = None
    return bool(ok)


def shutdown_terminal() -> None:
    global _CONNECTED_LOGIN, _LAST_HEARTBEAT
    if mt5 is not None:
        try:
            mt5.shutdown()
        except Exception:
            pass
    _CONNECTED_LOGIN = None
    _LAST_HEARTBEAT = None


def account_type_from_info(info) -> str:
    if mt5 is None:
        return "demo"
    real_value = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", 2)
    return "live" if int(getattr(info, "trade_mode", 0)) == int(real_value) else "demo"


def _profile_from_info(info, nickname: str | None = None, broker: str | None = None) -> dict[str, Any]:
    global _LAST_HEARTBEAT
    login = int(info.login)
    floating = float(info.profit or 0)
    _LAST_HEARTBEAT = _now_iso()
    state = read_state()
    old = next((p for p in state.get("profiles", []) if int(p.get("login", 0)) == login), {})
    return {
        "id": int(old.get("id", 0) or 0),
        "login": login,
        "nickname": nickname or old.get("nickname") or f"MT5 #{login}",
        "broker": broker or old.get("broker") or str(getattr(info, "company", "MetaTrader 5") or "MetaTrader 5"),
        "server": str(getattr(info, "server", "") or old.get("server") or ""),
        "balance": float(info.balance or 0),
        "equity": float(info.equity or 0),
        "margin": float(info.margin or 0),
        "free_margin": float(info.margin_free or 0),
        "floating_pl": floating,
        "leverage": int(info.leverage or 0),
        "currency": str(info.currency or ""),
        "status": "connected",
        "is_active": True,
        "account_type": account_type_from_info(info),
        "worker_id": "local-python-bridge",
        "terminal_id": Path(_terminal_path()).stem if _terminal_path() else "auto-detected-terminal",
        "connection_status": "online",
        "last_heartbeat": _LAST_HEARTBEAT,
        "created_at": old.get("created_at") or _now_iso(),
    }


def current_account_info():
    global _CONNECTED_LOGIN, _LAST_HEARTBEAT, _LAST_ERROR
    if mt5 is None:
        return None
    try:
        info = mt5.account_info()
    except Exception as exc:
        _LAST_ERROR = str(exc)
        return None
    if info is None:
        return None
    _CONNECTED_LOGIN = int(info.login)
    _LAST_HEARTBEAT = _now_iso()
    _LAST_ERROR = None
    return info


def connect_account(login: int, password: str | None, server: str | None, nickname: str | None = None, broker: str | None = None) -> dict[str, Any]:
    global _CONNECTED_LOGIN
    with _LOCK:
        # Initialize with explicit credentials. If password is omitted, MT5 may use credentials saved in the terminal.
        if not initialize_terminal(login=int(login), password=password or None, server=server or None):
            raise RuntimeError(f"MT5 connection failed: {last_error_text()}")
        info = current_account_info()
        if info is None or int(info.login) != int(login):
            raise RuntimeError(f"MT5 login failed for #{login}: {last_error_text()}")
        _CONNECTED_LOGIN = int(info.login)
        profile = _profile_from_info(info, nickname=nickname, broker=broker)
        if profile.get("id") == 0:
            profile.pop("id", None)
        return upsert_profile(profile)


def test_account(login: int, password: str | None, server: str | None) -> dict[str, Any]:
    with _LOCK:
        if not initialize_terminal(login=int(login), password=password or None, server=server or None):
            raise RuntimeError(f"MT5 connection test failed: {last_error_text()}")
        info = current_account_info()
        if info is None or int(info.login) != int(login):
            raise RuntimeError(f"MT5 login test failed for #{login}: {last_error_text()}")
        return {
            "ok": True,
            "mode": "bridge",
            "message": f"Connected to {getattr(info, 'server', server or 'MT5 server')} as #{int(info.login)} ({account_type_from_info(info).upper()}).",
        }


def reconnect_profile(login: int) -> dict[str, Any]:
    state = read_state()
    profile = next((p for p in state.get("profiles", []) if int(p.get("login", 0)) == int(login)), None)
    if not profile:
        raise RuntimeError("Account profile not found.")
    # No password is stored by KOOLKID. MT5 can reuse credentials saved by the terminal if available.
    return connect_account(int(login), None, str(profile.get("server") or "") or None, profile.get("nickname"), profile.get("broker"))


def list_accounts() -> list[dict[str, Any]]:
    state = read_state()
    info = current_account_info()
    connected_login = int(info.login) if info is not None else None
    rows: list[dict[str, Any]] = []
    for profile in state.get("profiles", []):
        row = dict(profile)
        row["status"] = "disconnected"
        row["is_active"] = int(row.get("login", 0)) == int(state.get("active_login") or 0)
        row["connection_status"] = "offline"
        if connected_login and int(row.get("login", 0)) == connected_login:
            live = _profile_from_info(info, row.get("nickname"), row.get("broker"))
            live["id"] = row.get("id")
            live["is_active"] = row["is_active"] or len(state.get("profiles", [])) == 1
            row.update(live)
            # Persist refreshed non-secret account metrics.
            upsert_profile(row, make_active=False)
        rows.append(row)
    # If terminal is connected but the account has not been added to the Hub yet, don't silently create it.
    return rows


def disconnect_account(login: int | None = None) -> None:
    info = current_account_info()
    if login is None or info is None or int(info.login) == int(login):
        shutdown_terminal()


def set_active_login(login: int) -> None:
    def mut(state):
        state["active_login"] = int(login)
        for row in state["profiles"]:
            row["is_active"] = int(row.get("login", 0)) == int(login)
        return True
    update_state(mut)


def bridge_status() -> dict[str, Any]:
    info = current_account_info()
    terminal = None
    trading_enabled = False
    message: str
    status = "offline"
    if mt5 is None:
        status = "error"
        message = "MetaTrader5 package is not installed in this Python environment."
    elif info is None:
        message = "Bridge is running locally. Connect an MT5 account from the Accounts page."
    else:
        status = "online"
        account_type = account_type_from_info(info)
        terminal_info = mt5.terminal_info()
        terminal = str(getattr(terminal_info, "path", "") or _terminal_path() or "MetaTrader 5")
        terminal_trade_allowed = bool(getattr(terminal_info, "trade_allowed", True)) if terminal_info else True
        account_trade_allowed = bool(getattr(info, "trade_allowed", True))
        trading_enabled = terminal_trade_allowed and account_trade_allowed
        terminal_api_disabled = bool(getattr(terminal_info, "tradeapi_disabled", False)) if terminal_info else False
        if terminal_api_disabled:
            message = "MT5 has disabled trading through the external Python API. Enable the terminal's external API permission before trading."
        elif not terminal_trade_allowed:
            message = "MT5 Algo Trading is disabled. Enable Algo Trading in the original bridge terminal before placing API trades."
        elif not account_trade_allowed:
            message = "The connected MT5 account currently does not allow trading."
        else:
            message = f"{account_type.upper()} account #{int(info.login)} connected to the local MT5 terminal."
    terminal_data_path = str(getattr(terminal_info, "data_path", "") or "") if info is not None and terminal_info else None
    tradeapi_disabled = bool(getattr(terminal_info, "tradeapi_disabled", False)) if info is not None and terminal_info else None
    return {
        "status": status,
        "mode": "bridge",
        "terminal": terminal,
        "terminal_path": terminal,
        "data_path": terminal_data_path,
        "trade_allowed": terminal_trade_allowed if info is not None else False,
        "tradeapi_disabled": tradeapi_disabled,
        "account_login": int(info.login) if info is not None else None,
        "account_server": str(getattr(info, "server", "") or "") if info is not None else None,
        "account_trade_allowed": account_trade_allowed if info is not None else False,
        "account_trade_expert": bool(getattr(info, "trade_expert", False)) if info is not None else False,
        "trading_enabled": trading_enabled,
        "endpoint": f"http://{os.getenv('MT5_BRIDGE_HOST', '127.0.0.1')}:{os.getenv('MT5_BRIDGE_PORT', '8000')}",
        "protocol": "Local HTTP → MetaTrader5 Python API",
        "last_heartbeat": _LAST_HEARTBEAT,
        "message": message,
        "capabilities": {
            "account_data": bool(info is not None),
            "quotes": bool(info is not None),
            "candles": bool(info is not None),
            "manual_trading": bool(trading_enabled),
            "positions": bool(info is not None),
            "history": bool(info is not None),
            "ea_launch": False,
        },
    }


def _ensure_connected(expected_login: int | None = None):
    info = current_account_info()
    if info is None:
        raise RuntimeError("No MT5 account is connected to the local bridge.")
    if expected_login is not None and int(info.login) != int(expected_login):
        raise RuntimeError(f"MT5 terminal is connected to #{int(info.login)}, not requested account #{int(expected_login)}.")
    return info


def _resolve_symbol(requested: str) -> str:
    module = _mt5_required()
    requested = requested.strip()
    direct = module.symbol_info(requested)
    if direct is not None:
        if not getattr(direct, "visible", True):
            module.symbol_select(requested, True)
        return requested
    symbols = module.symbols_get() or ()
    req = requested.upper()
    candidates = [s.name for s in symbols if str(s.name).upper() == req]
    if not candidates:
        candidates = [s.name for s in symbols if str(s.name).upper().startswith(req)]
    if not candidates:
        raise RuntimeError(f"Symbol '{requested}' was not found in the connected MT5 terminal.")
    candidates.sort(key=lambda x: (len(x), x))
    resolved = candidates[0]
    module.symbol_select(resolved, True)
    return resolved


def quotes(symbols: Iterable[str]) -> list[dict[str, Any]]:
    _ensure_connected()
    module = _mt5_required()
    rows = []
    for requested in symbols:
        try:
            resolved = _resolve_symbol(requested)
            info = module.symbol_info(resolved)
            tick = module.symbol_info_tick(resolved)
            if info is None or tick is None:
                continue
            bid = float(tick.bid or 0)
            ask = float(tick.ask or 0)
            last = float(tick.last or bid or ask or 0)
            rows.append({
                "symbol": requested,
                "resolved_symbol": resolved,
                "bid": bid,
                "ask": ask,
                "last": last,
                "digits": int(info.digits or 0),
                "point": float(info.point or 0),
                "spread_points": float((ask - bid) / info.point) if info.point else float(getattr(info, "spread", 0) or 0),
                "time": datetime.fromtimestamp(int(tick.time), tz=timezone.utc).isoformat() if getattr(tick, "time", 0) else _now_iso(),
                "trade_allowed": int(getattr(info, "trade_mode", 0)) != int(getattr(module, "SYMBOL_TRADE_MODE_DISABLED", -1)),
            })
        except Exception:
            continue
    return rows


_TF_MAP_NAMES = {
    "M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1",
}


def candles(symbol: str, timeframe: str, count: int = 220) -> list[dict[str, Any]]:
    _ensure_connected()
    module = _mt5_required()
    tf_name = _TF_MAP_NAMES.get(timeframe.upper())
    if not tf_name or not hasattr(module, tf_name):
        raise RuntimeError(f"Unsupported timeframe '{timeframe}'.")
    resolved = _resolve_symbol(symbol)
    rates = module.copy_rates_from_pos(resolved, getattr(module, tf_name), 0, max(10, min(int(count), 1000)))
    if rates is None:
        raise RuntimeError(f"Could not load {symbol} candles: {last_error_text()}")
    out = []
    for r in rates:
        out.append({
            "time": int(r["time"]),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r["tick_volume"]),
        })
    return out


def _source_from_comment(comment: str | None) -> str:
    text = str(comment or "").strip()
    if text.lower().startswith("koolkid hub"):
        return "Manual"
    if text.lower().startswith("koolkid:"):
        return text.split(":", 1)[1].strip() or "MT5"
    return text or "MT5"


def list_positions() -> list[dict[str, Any]]:
    info = _ensure_connected()
    module = _mt5_required()
    rows = module.positions_get()
    if rows is None:
        raise RuntimeError(f"Could not read MT5 positions: {last_error_text()}")
    result = []
    for p in rows:
        is_buy = int(p.type) == int(module.POSITION_TYPE_BUY)
        result.append({
            "id": int(p.ticket),
            "ticket": int(p.ticket),
            "account_login": int(info.login),
            "symbol": str(p.symbol),
            "type": "buy" if is_buy else "sell",
            "volume": float(p.volume),
            "open_price": float(p.price_open),
            "current_price": float(p.price_current),
            "sl": float(p.sl) if float(p.sl or 0) else None,
            "tp": float(p.tp) if float(p.tp or 0) else None,
            "profit": float(p.profit or 0),
            "swap": float(getattr(p, "swap", 0) or 0),
            "commission": 0.0,
            "open_time": datetime.fromtimestamp(int(p.time), tz=timezone.utc).isoformat(),
            "source": _source_from_comment(getattr(p, "comment", "")),
            "magic": int(getattr(p, "magic", 0) or 0) or None,
        })
    return result


def _history_deals(days: int | None = None):
    _ensure_connected()
    module = _mt5_required()
    history_days = int(days or os.getenv("MT5_HISTORY_DAYS", "30") or 30)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, history_days))
    deals = module.history_deals_get(start, end)
    if deals is None:
        raise RuntimeError(f"Could not read MT5 deal history: {last_error_text()}")
    return deals


def _closed_rows_from_deals(deals) -> list[dict[str, Any]]:
    module = _mt5_required()
    buy_type = int(module.DEAL_TYPE_BUY)
    sell_type = int(module.DEAL_TYPE_SELL)
    entry_in = int(module.DEAL_ENTRY_IN)
    entry_out = int(module.DEAL_ENTRY_OUT)
    entry_inout = int(module.DEAL_ENTRY_INOUT)
    entry_out_by = int(getattr(module, "DEAL_ENTRY_OUT_BY", 3))
    groups: dict[int, list[Any]] = defaultdict(list)
    for d in deals:
        if int(getattr(d, "type", -999)) not in {buy_type, sell_type}:
            continue
        pos_id = int(getattr(d, "position_id", 0) or 0)
        if pos_id:
            groups[pos_id].append(d)

    rows = []
    for pos_id, ds in groups.items():
        ds.sort(key=lambda d: (int(getattr(d, "time_msc", 0) or 0), int(getattr(d, "ticket", 0) or 0)))
        entries = [d for d in ds if int(getattr(d, "entry", -1)) in {entry_in, entry_inout}]
        exits = [d for d in ds if int(getattr(d, "entry", -1)) in {entry_out, entry_inout, entry_out_by}]
        if not entries or not exits:
            continue
        first = entries[0]
        open_volume = sum(float(getattr(d, "volume", 0) or 0) for d in entries)
        close_volume = sum(float(getattr(d, "volume", 0) or 0) for d in exits)
        open_price = sum(float(d.price) * float(d.volume) for d in entries) / open_volume if open_volume else float(first.price)
        close_price = sum(float(d.price) * float(d.volume) for d in exits) / close_volume if close_volume else float(exits[-1].price)
        profit = sum(float(getattr(d, "profit", 0) or 0) for d in ds)
        swap = sum(float(getattr(d, "swap", 0) or 0) for d in ds)
        commission = sum(float(getattr(d, "commission", 0) or 0) for d in ds) + sum(float(getattr(d, "fee", 0) or 0) for d in ds)
        comments = [str(getattr(d, "comment", "") or "") for d in ds]
        source = "Manual" if any(x.lower().startswith("koolkid hub") for x in comments) else _source_from_comment(next((x for x in comments if x), ""))
        rows.append({
            "id": pos_id,
            "ticket": pos_id,
            "account_login": int(getattr(first, "login", 0) or 0),
            "symbol": str(first.symbol),
            "type": "buy" if int(first.type) == buy_type else "sell",
            "volume": float(max(open_volume, close_volume)),
            "open_price": float(open_price),
            "close_price": float(close_price),
            "profit": float(profit),
            "swap": float(swap),
            "commission": float(commission),
            "net_pl": float(profit + swap + commission),
            "open_time": datetime.fromtimestamp(int(entries[0].time), tz=timezone.utc).isoformat(),
            "close_time": datetime.fromtimestamp(int(exits[-1].time), tz=timezone.utc).isoformat(),
            "source": source,
        })
    rows.sort(key=lambda r: r["close_time"], reverse=True)
    return rows


def history_rows(days: int | None = None) -> list[dict[str, Any]]:
    info = _ensure_connected()
    rows = _closed_rows_from_deals(_history_deals(days))
    for row in rows:
        if not row.get("account_login"):
            row["account_login"] = int(info.login)
    return rows


def _filling_candidates(symbol_info) -> list[int]:
    module = _mt5_required()
    candidates: list[int] = []
    mode = int(getattr(symbol_info, "filling_mode", 0) or 0)
    symbol_fok = int(getattr(module, "SYMBOL_FILLING_FOK", 1))
    symbol_ioc = int(getattr(module, "SYMBOL_FILLING_IOC", 2))
    if mode & symbol_fok:
        candidates.append(int(module.ORDER_FILLING_FOK))
    if mode & symbol_ioc:
        candidates.append(int(module.ORDER_FILLING_IOC))
    for candidate in [int(module.ORDER_FILLING_IOC), int(module.ORDER_FILLING_FOK), int(module.ORDER_FILLING_RETURN)]:
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _check_trading_permission(info) -> None:
    module = _mt5_required()
    terminal_info = module.terminal_info()
    if terminal_info is not None and bool(getattr(terminal_info, "tradeapi_disabled", False)):
        raise RuntimeError("MT5 has disabled trading through the external Python API. Enable the terminal's external API permission first.")
    if terminal_info is not None and not bool(getattr(terminal_info, "trade_allowed", True)):
        raise RuntimeError("MT5 terminal has algorithmic/API trading disabled. Enable trading permission in MetaTrader 5 first.")
    if not bool(getattr(info, "trade_allowed", True)):
        raise RuntimeError("This MT5 account currently does not allow trading.")
    # LIVE authorization is handled by the Hub/EA-worker request layer.
    # This low-level check enforces only real MT5 terminal/account permissions.


def _time_in_window(window: str) -> bool:
    try:
        start_s, end_s = window.split("-", 1)
        sh, sm = [int(x) for x in start_s.split(":", 1)]
        eh, em = [int(x) for x in end_s.split(":", 1)]
        now = datetime.now().time()
        start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
        end = now.replace(hour=eh, minute=em, second=59, microsecond=999999)
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end
    except Exception:
        return True


def _applicable_risk(login: int) -> list[dict[str, Any]]:
    state = read_state()
    rows = []
    for r in state.get("risk", []):
        if not r.get("auto_stop", True):
            continue
        if r.get("scope") == "global":
            rows.append(r)
        elif r.get("scope") == "account" and int(r.get("account_login") or 0) == int(login):
            rows.append(r)
    return rows


def _enforce_risk(login: int, symbol: str, volume: float, side: str, sl: float | None, entry_price: float) -> None:
    info = _ensure_connected(login)
    module = _mt5_required()
    positions = list_positions()
    history = history_rows(days=2)
    today = datetime.now(timezone.utc).date().isoformat()
    today_rows = [r for r in history if str(r["close_time"]).startswith(today)]
    realized = sum(float(r["profit"]) + float(r["swap"]) + float(r["commission"]) for r in today_rows)
    for rule in _applicable_risk(login):
        allowed = [str(x).upper() for x in rule.get("allowed_symbols", [])]
        if allowed and symbol.upper() not in allowed:
            raise RuntimeError(f"Risk limit: {symbol} is not in the allowed-symbol list.")
        if not _time_in_window(str(rule.get("allowed_trading_hours") or "00:00-23:59")):
            raise RuntimeError(f"Risk limit: trading is outside allowed hours ({rule.get('allowed_trading_hours')}).")
        max_lot = float(rule.get("max_lot_size") or 0)
        if max_lot > 0 and volume > max_lot:
            raise RuntimeError(f"Risk limit: volume {volume:.2f} exceeds max lot size {max_lot:.2f}.")
        max_pos = int(rule.get("max_open_positions") or 0)
        if max_pos > 0 and len(positions) >= max_pos:
            raise RuntimeError(f"Risk limit: maximum {max_pos} open positions reached.")
        max_trades = int(rule.get("max_trades_per_day") or 0)
        if max_trades > 0 and len(today_rows) >= max_trades:
            raise RuntimeError(f"Risk limit: maximum {max_trades} closed trades per day reached.")
        max_loss = float(rule.get("max_daily_loss") or 0)
        if max_loss > 0 and realized <= -abs(max_loss):
            raise RuntimeError(f"Risk limit: daily loss stop of ${max_loss:.2f} has been reached.")
        max_profit = float(rule.get("max_daily_profit") or 0)
        if max_profit > 0 and realized >= abs(max_profit):
            raise RuntimeError(f"Risk limit: daily profit stop of ${max_profit:.2f} has been reached.")
        max_dd = float(rule.get("max_drawdown_pct") or 0)
        balance = float(info.balance or 0)
        equity = float(info.equity or 0)
        dd = max(0.0, ((balance - equity) / balance) * 100.0) if balance > 0 else 0.0
        if max_dd > 0 and dd >= max_dd:
            raise RuntimeError(f"Risk limit: current account drawdown {dd:.2f}% reached the {max_dd:.2f}% limit.")
        max_risk_pct = float(rule.get("max_risk_per_trade") or 0)
        if max_risk_pct > 0 and sl and entry_price > 0 and float(info.equity or 0) > 0:
            resolved = _resolve_symbol(symbol)
            order_type = module.ORDER_TYPE_BUY if side == "buy" else module.ORDER_TYPE_SELL
            projected = module.order_calc_profit(order_type, resolved, volume, entry_price, float(sl))
            if projected is not None:
                risk_pct = abs(float(projected)) / float(info.equity) * 100.0
                if risk_pct > max_risk_pct:
                    raise RuntimeError(f"Risk limit: SL implies about {risk_pct:.2f}% account risk, above the {max_risk_pct:.2f}% limit.")


def _send_market_request(request: dict[str, Any], symbol_info):
    module = _mt5_required()
    last = None
    for filling in _filling_candidates(symbol_info):
        req = dict(request)
        req["type_filling"] = filling
        check = module.order_check(req)
        if check is None:
            last = f"order_check failed: {last_error_text()}"
            continue
        if int(getattr(check, "retcode", 1)) != 0:
            # Some terminals return a nonzero retcode in check for filling-mode issues. Try the next allowed mode.
            last = str(getattr(check, "comment", "Order check failed"))
            continue
        result = module.order_send(req)
        if result is None:
            last = f"order_send failed: {last_error_text()}"
            continue
        retcode = int(result.retcode)
        success = {int(module.TRADE_RETCODE_DONE), int(getattr(module, "TRADE_RETCODE_DONE_PARTIAL", module.TRADE_RETCODE_DONE))}
        if retcode in success:
            return result
        last = f"MT5 rejected order ({retcode}): {getattr(result, 'comment', 'unknown error')}"
        invalid_fill = int(getattr(module, "TRADE_RETCODE_INVALID_FILL", -1))
        if retcode != invalid_fill:
            break
    raise RuntimeError(last or "MT5 order failed.")


def open_trade(login: int, symbol: str, side: str, volume: float, sl: float | None = None, tp: float | None = None) -> dict[str, Any]:
    module = _mt5_required()
    with _LOCK:
        info = _ensure_connected(login)
        _check_trading_permission(info)
        resolved = _resolve_symbol(symbol)
        sinfo = module.symbol_info(resolved)
        tick = module.symbol_info_tick(resolved)
        if sinfo is None or tick is None:
            raise RuntimeError(f"No live quote available for {symbol}.")
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise RuntimeError("Trade type must be buy or sell.")
        order_type = module.ORDER_TYPE_BUY if side == "buy" else module.ORDER_TYPE_SELL
        price = float(tick.ask if side == "buy" else tick.bid)
        volume = float(volume)
        min_vol = float(sinfo.volume_min or 0.01)
        max_vol = float(sinfo.volume_max or volume)
        step = float(sinfo.volume_step or min_vol or 0.01)
        if volume < min_vol or volume > max_vol:
            raise RuntimeError(f"Volume must be between {min_vol:g} and {max_vol:g} lots for {resolved}.")
        snapped = round(round(volume / step) * step, 8)
        if not math.isclose(snapped, volume, rel_tol=0, abs_tol=max(step / 100, 1e-8)):
            raise RuntimeError(f"Volume must follow the broker step of {step:g} lots for {resolved}.")
        _enforce_risk(login, symbol, volume, side, sl, price)
        before = {int(p.ticket) for p in (module.positions_get() or ())}
        request = {
            "action": module.TRADE_ACTION_DEAL,
            "symbol": resolved,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": float(sl or 0),
            "tp": float(tp or 0),
            "deviation": int(os.getenv("MT5_DEVIATION_POINTS", "20") or 20),
            "magic": int(os.getenv("MT5_MAGIC", "510999") or 510999),
            "comment": "KOOLKID Hub",
            "type_time": module.ORDER_TIME_GTC,
        }
        _send_market_request(request, sinfo)
        time.sleep(0.15)
        positions = list_positions()
        newly_opened = [p for p in positions if int(p["ticket"]) not in before]
        candidates = newly_opened or [p for p in positions if p["symbol"] == resolved]
        if not candidates:
            raise RuntimeError("MT5 accepted the deal, but the resulting position could not be found. Refresh Positions to verify the account.")
        candidates.sort(key=lambda p: p["open_time"], reverse=True)
        return candidates[0]


def _position_namedtuple(ticket: int):
    module = _mt5_required()
    rows = module.positions_get(ticket=int(ticket))
    if not rows:
        raise RuntimeError(f"Open position #{ticket} was not found.")
    return rows[0]


def close_position(ticket: int) -> dict[str, Any]:
    module = _mt5_required()
    with _LOCK:
        info = _ensure_connected()
        _check_trading_permission(info)
        p = _position_namedtuple(ticket)
        resolved = str(p.symbol)
        sinfo = module.symbol_info(resolved)
        tick = module.symbol_info_tick(resolved)
        if sinfo is None or tick is None:
            raise RuntimeError(f"No live quote available for {resolved}.")
        original_buy = int(p.type) == int(module.POSITION_TYPE_BUY)
        close_type = module.ORDER_TYPE_SELL if original_buy else module.ORDER_TYPE_BUY
        price = float(tick.bid if original_buy else tick.ask)
        request = {
            "action": module.TRADE_ACTION_DEAL,
            "position": int(p.ticket),
            "symbol": resolved,
            "volume": float(p.volume),
            "type": close_type,
            "price": price,
            "deviation": int(os.getenv("MT5_DEVIATION_POINTS", "20") or 20),
            "magic": int(os.getenv("MT5_MAGIC", "510999") or 510999),
            "comment": "KOOLKID Hub close",
            "type_time": module.ORDER_TIME_GTC,
        }
        _send_market_request(request, sinfo)
        time.sleep(0.15)
        deals = module.history_deals_get(position=int(p.ticket)) or ()
        rows = _closed_rows_from_deals(deals)
        if rows:
            closed = rows[0]
            closed["account_login"] = int(info.login)
            return {"ok": True, "profit": float(closed["profit"] + closed["swap"] + closed["commission"]), "closed": closed}
        closed = {
            "id": int(p.ticket), "ticket": int(p.ticket), "account_login": int(info.login), "symbol": resolved,
            "type": "buy" if original_buy else "sell", "volume": float(p.volume), "open_price": float(p.price_open),
            "close_price": price, "profit": 0.0, "swap": float(getattr(p, "swap", 0) or 0), "commission": 0.0,
            "net_pl": float(getattr(p, "swap", 0) or 0),
            "open_time": datetime.fromtimestamp(int(p.time), tz=timezone.utc).isoformat(), "close_time": _now_iso(), "source": _source_from_comment(getattr(p, "comment", "")),
        }
        return {"ok": True, "profit": float(closed["net_pl"]), "closed": closed}


def close_all_positions() -> dict[str, Any]:
    positions = list_positions()
    closed = 0
    realized = 0.0
    errors = []
    for p in positions:
        try:
            result = close_position(int(p["ticket"]))
            closed += 1
            realized += float(result.get("profit", 0) or 0)
        except Exception as exc:
            errors.append(f"#{p['ticket']}: {exc}")
    if errors:
        raise RuntimeError(f"Closed {closed}/{len(positions)} positions. " + " | ".join(errors[:4]))
    return {"ok": True, "closed": closed, "realized": round(realized, 2)}


def account_stats() -> dict[str, Any]:
    info = _ensure_connected()
    positions = list_positions()
    history = history_rows()
    today = datetime.now(timezone.utc).date().isoformat()
    today_rows = [r for r in history if str(r["close_time"]).startswith(today)]
    net = lambda r: float(r["profit"]) + float(r["swap"]) + float(r["commission"])
    realized_today = sum(net(r) for r in today_rows)
    floating = sum(float(p["profit"]) + float(p["swap"]) for p in positions)
    wins = [r for r in history if net(r) > 0]
    balance = float(info.balance or 0)
    equity = float(info.equity or 0)
    margin = float(info.margin or 0)
    free_margin = float(info.margin_free or 0)
    start_equity = balance - sum(net(r) for r in history)
    daily_map: dict[str, float] = defaultdict(float)
    for r in history:
        daily_map[str(r["close_time"])[:10]] += net(r)
    curve = start_equity
    equity_points = []
    daily = []
    for day in sorted(daily_map):
        curve += daily_map[day]
        daily.append({"date": day, "pl": round(daily_map[day], 2)})
        equity_points.append({"date": day, "equity": round(curve, 2), "daily_pl": round(daily_map[day], 2)})
    if not equity_points:
        day = datetime.now(timezone.utc).date().isoformat()
        equity_points.append({"date": day, "equity": round(equity, 2), "daily_pl": round(realized_today, 2)})
    peak = max([p["equity"] for p in equity_points] + [equity])
    dd = max(0.0, (peak - equity) / peak * 100.0) if peak > 0 else 0.0
    exposure_map: dict[str, dict[str, Any]] = {}
    for p in positions:
        row = exposure_map.setdefault(p["symbol"], {"symbol": p["symbol"], "volume": 0.0, "floating": 0.0, "count": 0})
        row["volume"] += float(p["volume"])
        row["floating"] += float(p["profit"]) + float(p["swap"])
        row["count"] += 1
    sym_map: dict[str, dict[str, Any]] = {}
    for r in history:
        row = sym_map.setdefault(r["symbol"], {"symbol": r["symbol"], "pl": 0.0, "trades": 0})
        row["pl"] += net(r)
        row["trades"] += 1
    state = read_state()
    bots = state.get("bots", [])
    running = sum(1 for b in bots if b.get("status") == "running")
    paused = sum(1 for b in bots if b.get("status") == "paused")
    return {
        "kpis": {
            "total_balance": balance,
            "total_equity": equity,
            "floating": floating,
            "margin": margin,
            "free_margin": free_margin,
            "margin_level": float(info.margin_level) if float(info.margin_level or 0) else None,
            "realized_today": round(realized_today, 2),
            "today_pl": round(realized_today + floating, 2),
            "trades_today": len(today_rows),
            "latest_day": max(daily_map) if daily_map else None,
            "connected_accounts": 1,
            "total_accounts": len(state.get("profiles", [])),
            "running_bots": running,
            "paused_bots": paused,
            "total_bots": len(bots),
            "open_positions": len(positions),
            "win_rate_30d": round((len(wins) / len(history) * 100.0), 1) if history else 0,
            "trades_30d": len(history),
            "profit_30d": round(sum(net(r) for r in history), 2),
            "drawdown_pct": round(dd, 2),
            "peak_equity": round(peak, 2),
        },
        "equity": equity_points,
        "daily": daily,
        "bots": bots,
        "symbolPnl": list(sym_map.values()),
        "exposure": list(exposure_map.values()),
    }


def symbol_catalog(visible_only: bool = True, limit: int = 1000) -> list[dict[str, Any]]:
    _ensure_connected()
    module = _mt5_required()
    symbols = module.symbols_get()
    if symbols is None:
        raise RuntimeError(f"Could not read MT5 symbols: {last_error_text()}")
    rows = []
    disabled_value = int(getattr(module, "SYMBOL_TRADE_MODE_DISABLED", -1))
    for s in symbols:
        if visible_only and not bool(getattr(s, "visible", False)):
            continue
        path = str(getattr(s, "path", "") or "")
        description = str(getattr(s, "description", "") or path or s.name)
        upper_hint = f"{s.name} {description} {path}".upper()
        clean_symbol = "".join(ch for ch in str(s.name).upper() if ch.isalpha())
        fx_codes = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SGD", "HKD", "NOK", "SEK", "ZAR", "TRY", "MXN", "CNH", "PLN", "HUF", "CZK"}
        looks_like_fx = len(clean_symbol) >= 6 and clean_symbol[:3] in fx_codes and clean_symbol[3:6] in fx_codes and clean_symbol[:3] != clean_symbol[3:6]
        if looks_like_fx or "FOREX" in upper_hint or "FX" in upper_hint:
            category = "Forex"
        elif any(token in upper_hint for token in ["VOLATILITY", "BOOM", "CRASH", "STEP", "JUMP", "RANGE BREAK", "SYNTHETIC", "DERIVED"]):
            category = "Synthetic / Volatility"
        elif any(token in upper_hint for token in ["GOLD", "SILVER", "XAU", "XAG", "METAL"]):
            category = "Metals"
        elif any(token in upper_hint for token in ["BTC", "ETH", "CRYPTO", "LTC", "XRP", "SOL"]):
            category = "Crypto"
        elif any(token in upper_hint for token in ["INDEX", "INDICES", "US30", "NAS", "SP500", "GER", "UK100", "JP225"]):
            category = "Indices"
        else:
            category = path.split("\\")[0] if path else "Other"
        rows.append({
            "symbol": str(s.name),
            "description": description,
            "path": path,
            "category": category,
            "digits": int(getattr(s, "digits", 0) or 0),
            "point": float(getattr(s, "point", 0) or 0),
            "contract_size": float(getattr(s, "trade_contract_size", 0) or 0),
            "volume_min": float(getattr(s, "volume_min", 0) or 0),
            "volume_max": float(getattr(s, "volume_max", 0) or 0),
            "volume_step": float(getattr(s, "volume_step", 0) or 0),
            "visible": bool(getattr(s, "visible", False)),
            "trade_allowed": int(getattr(s, "trade_mode", disabled_value)) != disabled_value,
        })
    rows.sort(key=lambda x: (not x["trade_allowed"], x["symbol"].upper()))
    return rows[: max(1, min(int(limit), 5000))]
