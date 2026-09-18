from __future__ import annotations
import configparser
import ctypes, json, os, queue, shlex, shutil, subprocess, threading, time, traceback
from collections import defaultdict
from ctypes import wintypes
from datetime import datetime, timedelta, timezone


def hide_terminal_windows(terminal_path):
    if os.name != "nt" or not terminal_path:
        return
    target_dir = os.path.normcase(os.path.dirname(os.path.abspath(terminal_path)))
    allowed = {"terminal64.exe", "metaeditor64.exe", "metatester64.exe"}
    user32, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def hide_if_target(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if handle:
            try:
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                    image = os.path.normcase(os.path.abspath(buffer.value))
                    if os.path.dirname(image) == target_dir and os.path.basename(image).lower() in allowed:
                        user32.ShowWindowAsync(hwnd, 0)
                        user32.ShowWindow(hwnd, 0)
                        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0080)
            finally:
                kernel.CloseHandle(handle)
        return True

    user32.EnumWindows(hide_if_target, 0)

def keep_terminal_hidden(terminal_path):
    started = time.monotonic()
    while True:
        hide_terminal_windows(terminal_path)
        time.sleep(0.01 if time.monotonic() - started < 5 else 0.20)


def write_bootstrap_config(terminal_path, login, server, credential):
    terminal_dir = os.path.dirname(os.path.abspath(terminal_path))
    config_dir = os.path.join(terminal_dir, "config")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, f".koolkid-bootstrap-{os.getpid()}-{threading.get_ident()}.ini")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.add_section("Common")
    parser.set("Common", "Login", str(int(login)))
    parser.set("Common", "Server", str(server))
    parser.set("Common", "Password", str(credential))
    parser.set("Common", "ProxyEnable", "0")
    parser.set("Common", "KeepPrivate", "0")
    parser.set("Common", "NewsEnable", "0")
    with open(config_path, "w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass
    return config_path


def launch_terminal_bootstrap(terminal_path, login, server, credential):
    config_path = write_bootstrap_config(terminal_path, login, server, credential)
    terminal_dir = os.path.dirname(os.path.abspath(terminal_path))
    args = [terminal_path, "/portable", f"/config:{config_path}"]
    startupinfo = None
    creationflags = 0
    try:
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()
        else:
            launcher = os.getenv("MT5_TERMINAL_LAUNCHER", "").strip()
            if launcher:
                args = [*shlex.split(launcher), *args]
            else:
                wine = shutil.which("wine64") or shutil.which("wine")
                if wine:
                    args = [wine, *args]
        subprocess.Popen(
            args, cwd=terminal_dir, startupinfo=startupinfo, creationflags=creationflags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(max(2.0, min(15.0, float(os.getenv("MT5_BOOTSTRAP_WAIT_SECONDS", "8")))))
        return True, ""
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            os.remove(config_path)
        except OSError:
            pass


def ensure_terminal_trading_permissions(terminal_path):
    """Prepare a private terminal for KOOLKID API/algo trading before MT5 starts."""
    if not terminal_path:
        return
    config_dir = os.path.join(os.path.dirname(os.path.abspath(terminal_path)), "config")
    os.makedirs(config_dir, exist_ok=True)
    common_ini = os.path.join(config_dir, "common.ini")
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    encoding = "utf-16"
    if os.path.isfile(common_ini):
        raw = open(common_ini, "rb").read()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        if raw:
            parser.read_string(raw.decode(encoding, errors="strict"))
    if not parser.has_section("Experts"):
        parser.add_section("Experts")
    # MT5 common.ini: Enabled=1 turns Algo Trading on; Api=0 keeps external
    # Python API trading enabled. These are terminal permissions, not a bypass
    # of broker/account-side restrictions.
    parser.set("Experts", "Enabled", "1")
    parser.set("Experts", "Api", "0")
    with open(common_ini, "w", encoding=encoding) as handle:
        parser.write(handle, space_around_delimiters=False)


def plain(obj):
    """Convert MT5 namedtuples, including nested request fields, for IPC."""
    if obj is None:
        return {}
    if hasattr(obj, "_asdict"):
        obj = obj._asdict()
    if isinstance(obj, dict):
        return {key: plain_value(value) for key, value in obj.items()}
    return {}


def plain_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "_asdict"):
        value = value._asdict()
    if isinstance(value, dict):
        return {key: plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_value(item) for item in value]
    return str(value)

HFM_SERVER_ENDPOINTS = {
    "HFMarketsGlobal-Demo": ["mt5-europe1.dcglobalfarm.com:1950", "mt5-europe2.dcglobalfarm.com:1950", "mt5-samerica.dcglobalfarm.com:1950", "mt5-asia1.dcglobalfarm.com:1950", "mt5-europe4.dcglobalfarm.com:1950", "mt5-asia7.dcglobalfarm.com:1950", "mt5-asia8.dcglobalfarm.com:1950"],
    "HFMarketsGlobal-Demo3": ["mt5-global3.dcglobalfarm.com:40305", "mt5-global3.dcglobalfarm.com:40306"],
    "HFMarketsGlobal-Demo4": ["mt5-ga-9.dcglobalfarm.com:40401", "mt5-ga-9.dcglobalfarm.com:40402", "mt5ds4dc.dcglobalfarm.com:40403"],
    "HFMarketsGlobal-Live1": ["mt5-europe1.dcglobalfarm.com:1951", "mt5-europe2.dcglobalfarm.com:1951", "mt5-samerica.dcglobalfarm.com:1951", "mt5-asia1.dcglobalfarm.com:1951", "mt5-europe4.dcglobalfarm.com:1951", "mt5-global.dcglobalfarm.com:450", "mt5-global.dcglobalfarm.com:451", "mt5-global.dcglobalfarm.com:452", "mt5-global.dcglobalfarm.com:453", "mt5-global.dcglobalfarm.com:550", "mt5-global.dcglobalfarm.com:551", "mt5-global.dcglobalfarm.com:552", "mt5-global.dcglobalfarm.com:553", "mt5-global.dcglobalfarm.com:1951"],
    "HFMarketsGlobal-Live3": ["mt5-global3.dcglobalfarm.com:709", "mt5-global3.dcglobalfarm.com:710", "mt5-global3.dcglobalfarm.com:20301", "mt5-global3.dcglobalfarm.com:20302"],
    "HFMarketsGlobal-Live4": ["mt5-global4.dcglobalfarm.com:20401", "mt5-global4.dcglobalfarm.com:20402", "mt5-live4-eu1.dcglobalfarm.com:20403"],
    "HFMarketsGlobal-Live5": ["mt5-global5.dcglobalfarm.com:20501", "mt5-global5.dcglobalfarm.com:20502"],
    "HFMarketsGlobal-Live7": ["mt5-global7.dcglobalfarm.com:20701", "mt5-global7.dcglobalfarm.com:20702"],
    "HFMarketsGlobal-Live8": ["mt5-global8.dcglobalfarm.com:20801", "mt5-global8.dcglobalfarm.com:20802"],
    "HFMarketsGlobal-Live9": ["mt5-global9.dcglobalfarm.com:20901", "mt5-global9.dcglobalfarm.com:20902"],
    "HFMarketsGlobal-Live10": ["mt5-global10.dcglobalfarm.com:21001", "mt5-global10.dcglobalfarm.com:21002"],
    "HFMarketsGlobal-Live11": ["mt5-global11.dcglobalfarm.com:21101", "mt5-global11.dcglobalfarm.com:21102"],
    "HFMarketsGlobal-Live12": ["mt5-ga-6.dcglobalfarm.com:21201", "mt5-ga-6.dcglobalfarm.com:21202", "mt5ls12dc.dcglobalfarm.com:21203"],
    "HFMarketsGlobal-Live13": ["mt5-ga-5.dcglobalfarm.com:21301", "mt5-ga-5.dcglobalfarm.com:21302", "mt5ls13dc.dcglobalfarm.com:21303"],
    "HFMarketsGlobal-Live14": ["mt5-ga-5.dcglobalfarm.com:21401", "mt5-ga-5.dcglobalfarm.com:21402", "mt5ls14dc.dcglobalfarm.com:21403"],
    "HFMarketsGlobal-Live15": ["mt5-ga-8.dcglobalfarm.com:21501", "mt5-ga-8.dcglobalfarm.com:21502", "mt5ls15dc.dcglobalfarm.com:21503"],
    "HFMarketsGlobal-Live16": ["mt5-ga-7.dcglobalfarm.com:21601", "mt5-ga-7.dcglobalfarm.com:21602", "mt5ls16dc.dcglobalfarm.com:21603"],
    "HFMarketsGlobal-Live17": ["mt5-ga-8.dcglobalfarm.com:21701", "mt5-ga-8.dcglobalfarm.com:21702", "mt5ls17dc.dcglobalfarm.com:21703"],
    "HFMarketsGlobal-Live18": ["mt5-ga-9.dcglobalfarm.com:21801", "mt5-ga-9.dcglobalfarm.com:21802", "mt5ls18dc.dcglobalfarm.com:21803"],
    "HFMarketsGlobal-Live19": ["mt5-ga-9.dcglobalfarm.com:21901", "mt5-ga-9.dcglobalfarm.com:21902", "mt5ls19dc.dcglobalfarm.com:21903"],
    "HFMarketsGlobal-Live20": ["mt5-ga-10.dcglobalfarm.com:22001", "mt5-ga-10.dcglobalfarm.com:22002", "mt5ls20dc.dcglobalfarm.com:22003"],
}


def configured_server_endpoints(broker, server):
    raw = os.getenv("MT5_SERVER_ENDPOINTS_JSON", "").strip()
    if not raw:
        return []
    try:
        mapping = json.loads(raw)
    except (TypeError, ValueError):
        return []
    broker_name = str(broker or "").strip()
    broker_map = mapping.get(broker_name) or mapping.get(broker_name.lower()) or {}
    value = broker_map.get(str(server or "").strip()) if isinstance(broker_map, dict) else None
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def mt5_server_candidates(broker, server):
    requested = str(server or "").strip()
    rows = [requested] if requested else [""]
    if str(broker or "").strip().lower() == "hfm":
        rows.extend(HFM_SERVER_ENDPOINTS.get(requested, []))
    rows.extend(configured_server_endpoints(broker, requested))
    return list(dict.fromkeys(rows))


def filling_candidates(mt5, info):
    candidates = []
    mode = int(info.get("filling_mode") or 0)
    if mode & int(getattr(mt5, "SYMBOL_FILLING_FOK", 1)):
        candidates.append(int(mt5.ORDER_FILLING_FOK))
    if mode & int(getattr(mt5, "SYMBOL_FILLING_IOC", 2)):
        candidates.append(int(mt5.ORDER_FILLING_IOC))
    for candidate in (int(mt5.ORDER_FILLING_IOC), int(mt5.ORDER_FILLING_FOK), int(mt5.ORDER_FILLING_RETURN)):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates

def send_market_order(mt5, request, info):
    success = {10008, 10009, 10010}
    invalid_fill = int(getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030))
    last = None
    for filling in filling_candidates(mt5, info):
        req = dict(request)
        req["type_filling"] = filling
        check = mt5.order_check(req)
        check_data = plain(check)
        if check is None:
            last = f"Order check failed: {mt5.last_error()}"
            continue
        if int(check_data.get("retcode", 1)) != 0:
            last = str(check_data.get("comment") or "Order check failed")
            continue
        order_send_started_at = time.time()
        result = mt5.order_send(req)
        order_send_result_at = time.time()
        out = plain(result)
        retcode = int(out.get("retcode", -1))
        if retcode in success:
            out["timing"] = {"order_send_started_at": order_send_started_at, "order_send_result_at": order_send_result_at}
            return out
        last = f"MT5 rejected order ({retcode}): {out.get('comment') or 'unknown error'}"
        if retcode != invalid_fill:
            break
    raise RuntimeError(last or "MT5 order failed")

def run_worker(config, password, command_q, response_q):
    mode = config["mode"]
    read_only = str(config.get("access_mode") or "trading").lower() == "investor"
    sim_positions = {}
    next_ticket = 100000
    mt5 = None

    try:
        if mode == "real":
            import MetaTrader5 as mt5_mod
            mt5 = mt5_mod
            terminal_path = config.get("terminal_path")
            if terminal_path and not read_only:
                ensure_terminal_trading_permissions(terminal_path)
            requested_server = str(config.get("server") or "").strip()
            kwargs = {
                "login": int(config["login"]),
                "timeout": int(os.getenv("MT5_WORKER_IPC_TIMEOUT_MS", "12000")),
            }
            if terminal_path:
                kwargs["path"] = terminal_path
            if password:
                kwargs["password"] = password
            if config.get("portable"):
                kwargs["portable"] = True

            bootstrap_done_marker = (
                os.path.join(os.path.dirname(os.path.abspath(terminal_path)), ".koolkid-headless-bootstrap-v1")
                if terminal_path else ""
            )
            if (
                terminal_path
                and config.get("broker_seeded")
                and password
                and requested_server
                and not os.path.isfile(bootstrap_done_marker)
            ):
                started, bootstrap_error = launch_terminal_bootstrap(
                    terminal_path, int(config["login"]), requested_server, password
                )
                if not started:
                    raise RuntimeError(f"Automatic MT5 broker bootstrap failed: {bootstrap_error}")

            def initialize_once():
                last_error = None
                server_candidates = mt5_server_candidates(config.get("broker"), requested_server)
                for server_candidate in server_candidates:
                    attempt = dict(kwargs)
                    if server_candidate:
                        attempt["server"] = server_candidate
                    if mt5.initialize(**attempt):
                        return server_candidate
                    last_error = mt5.last_error()
                    try:
                        mt5.shutdown()
                    except Exception:
                        pass

                # Some broker servers are not present in the generic terminal's
                # local directory. Start the private terminal first, then ask
                # MetaTrader to authenticate against the exact server separately.
                base_kwargs = {"timeout": kwargs["timeout"]}
                if terminal_path:
                    base_kwargs["path"] = terminal_path
                if config.get("portable"):
                    base_kwargs["portable"] = True
                if mt5.initialize(**base_kwargs):
                    try:
                        for server_candidate in server_candidates:
                            login_kwargs = {
                                "login": int(config["login"]),
                                "password": password or "",
                                "timeout": kwargs["timeout"],
                            }
                            if server_candidate:
                                login_kwargs["server"] = server_candidate
                            if mt5.login(**login_kwargs):
                                return server_candidate
                            last_error = mt5.last_error()
                    finally:
                        if mt5.account_info() is None:
                            try:
                                mt5.shutdown()
                            except Exception:
                                pass
                else:
                    last_error = mt5.last_error()

                error_code = last_error[0] if isinstance(last_error, (tuple, list)) and last_error else None
                error_text = str(last_error).lower()
                if terminal_path and (error_code == -10005 or "ipc timeout" in error_text):
                    if config.get("broker_seeded"):
                        if bootstrap_done_marker:
                            try:
                                os.remove(bootstrap_done_marker)
                            except OSError:
                                pass
                        raise RuntimeError(
                            f"Automatic MT5 broker bootstrap could not attach to server '{requested_server}'. "
                            "Retry the connection once; if it repeats, check the broker server or cloud MT5 runtime."
                        )
                    try:
                        marker = os.path.join(os.path.dirname(os.path.abspath(terminal_path)), ".koolkid-broker-bootstrap-required")
                        with open(marker, "w", encoding="utf-8") as handle:
                            handle.write(f"{config.get('broker') or 'MT5'}|{requested_server}|{config.get('login')}\n")
                    except Exception:
                        pass
                    raise RuntimeError(
                        "MT5 broker setup required. In the MT5 window that opened, log in once using this account "
                        f"and server '{requested_server}'. Keep that window open, then click Connect again in KOOLKID."
                    )
                raise RuntimeError(f"MT5 initialize/login failed: {last_error}")

            initialize_once()
            if terminal_path:
                try:
                    os.remove(os.path.join(os.path.dirname(os.path.abspath(terminal_path)), ".koolkid-broker-bootstrap-required"))
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            if os.name == "nt" and terminal_path:
                threading.Thread(target=keep_terminal_hidden, args=(terminal_path,), daemon=True).start()
            terminal_state = mt5.terminal_info()
            if not read_only and terminal_path and terminal_state is not None and (
                not bool(getattr(terminal_state, "trade_allowed", True))
                or bool(getattr(terminal_state, "tradeapi_disabled", False))
            ):
                # Some MT5 builds rewrite common.ini during first launch. Apply
                # the KOOLKID terminal policy once more and restart this private
                # terminal before accepting the account session.
                mt5.shutdown()
                ensure_terminal_trading_permissions(terminal_path)
                time.sleep(0.25)
                initialize_once()
                terminal_state = mt5.terminal_info()
                if terminal_state is not None and (
                    not bool(getattr(terminal_state, "trade_allowed", True))
                    or bool(getattr(terminal_state, "tradeapi_disabled", False))
                ):
                    mt5.shutdown()
                    raise RuntimeError("MT5 terminal could not enable algorithmic/API trading for this private KOOLKID session.")

            connected = mt5.account_info()
            actual_login = int(getattr(connected, "login", 0) or 0) if connected is not None else 0
            if actual_login != int(config["login"]):
                mt5.shutdown()
                raise RuntimeError(f"MT5 worker connected account #{actual_login or 'none'} instead of #{config['login']}.")
            actual_server = str(getattr(connected, "server", "") or "").strip() if connected is not None else ""
            # Named server selections from the UI must resolve to that exact MT5
            # server. Direct host:port entries are allowed to resolve to the
            # broker's canonical server name after authentication.
            if requested_server and "." not in requested_server and ":" not in requested_server:
                if requested_server.replace(" ", "").lower() != actual_server.replace(" ", "").lower():
                    mt5.shutdown()
                    raise RuntimeError(f"MT5 connected to '{actual_server or 'unknown'}' instead of selected server '{requested_server}'.")
            if config.get("broker_seeded") and bootstrap_done_marker:
                try:
                    with open(bootstrap_done_marker, "w", encoding="ascii") as handle:
                        handle.write("Headless broker bootstrap completed.\n")
                except OSError:
                    pass
        response_q.put({"id": "__startup__", "ok": True})
    except Exception as exc:
        response_q.put({"id": "__startup__", "ok": False, "error": str(exc)})
        return

    def account_info():
        if mode == "simulation":
            return {
                "login": int(config["login"]),
                "server": "KOOLKID-SIM",
                "balance": 10000.0,
                "equity": 10000.0,
                "currency": "USD",
                "access_mode": "investor" if read_only else "trading",
                "read_only": read_only,
            }
        info = mt5.account_info()
        terminal = mt5.terminal_info()
        if info is None or terminal is None:
            raise RuntimeError(f"MT5 account session is no longer responding: {mt5.last_error()}")
        result = plain(info)
        result.update({
            "terminal_path": str(getattr(terminal, "path", "") or ""),
            "data_path": str(getattr(terminal, "data_path", "") or ""),
            "terminal_trade_allowed": bool(getattr(terminal, "trade_allowed", False)),
            "tradeapi_disabled": bool(getattr(terminal, "tradeapi_disabled", False)),
            "access_mode": "investor" if read_only else "trading",
            "read_only": read_only,
        })
        return result

    def positions():
        if mode == "simulation":
            return list(sim_positions.values())
        return [plain(x) for x in (mt5.positions_get() or [])]

    def symbol_info(symbol):
        if mode == "simulation":
            return {"name": symbol, "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01}
        info = mt5.symbol_info(symbol)
        if info is None:
            return {}
        if not info.visible:
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
        return plain(info)

    def symbol_catalog(p):
        if mode == "simulation":
            return []
        visible_only = bool(p.get("visible_only", True))
        limit = max(1, min(int(p.get("limit") or 1000), 5000))
        rows = []
        disabled = int(getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", -1))
        for item in mt5.symbols_get() or []:
            if visible_only and not bool(getattr(item, "visible", False)):
                continue
            info = plain(item)
            rows.append({
                "symbol": str(item.name), "description": str(getattr(item, "description", "") or item.name),
                "path": str(getattr(item, "path", "") or ""), "category": str(getattr(item, "path", "Other") or "Other").split("\\")[0],
                "digits": int(getattr(item, "digits", 0) or 0), "point": float(getattr(item, "point", 0) or 0),
                "contract_size": float(getattr(item, "trade_contract_size", 0) or 0),
                "volume_min": float(getattr(item, "volume_min", 0) or 0), "volume_max": float(getattr(item, "volume_max", 0) or 0),
                "volume_step": float(getattr(item, "volume_step", 0) or 0), "visible": bool(getattr(item, "visible", False)),
                "trade_allowed": int(info.get("trade_mode", disabled)) != disabled,
            })
        return rows[:limit]

    def quotes(p):
        if mode == "simulation":
            return []
        rows = []
        disabled = int(getattr(mt5, "SYMBOL_TRADE_MODE_DISABLED", -1))
        for requested in p.get("symbols") or []:
            info = symbol_info(str(requested))
            if not info:
                continue
            resolved = str(info.get("name") or requested)
            tick = mt5.symbol_info_tick(resolved)
            if tick is None:
                continue
            bid, ask = float(tick.bid or 0), float(tick.ask or 0)
            point = float(info.get("point") or 0)
            rows.append({
                "symbol": str(requested), "resolved_symbol": resolved, "bid": bid, "ask": ask,
                "last": float(tick.last or bid or ask or 0), "digits": int(info.get("digits") or 0), "point": point,
                "spread_points": float((ask - bid) / point) if point else float(info.get("spread") or 0),
                "time": datetime.fromtimestamp(int(tick.time), timezone.utc).isoformat() if tick.time else datetime.now(timezone.utc).isoformat(),
                "trade_allowed": int(info.get("trade_mode", disabled)) != disabled,
            })
        return rows

    def candles(p):
        if mode == "simulation":
            return []
        names = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5", "M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30", "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4", "D1": "TIMEFRAME_D1"}
        timeframe = str(p.get("timeframe") or "M15").upper()
        if timeframe not in names:
            raise RuntimeError(f"Unsupported timeframe '{timeframe}'.")
        info = symbol_info(str(p["symbol"]))
        if not info:
            raise RuntimeError(f"Symbol unavailable: {p['symbol']}")
        rates = mt5.copy_rates_from_pos(str(info.get("name") or p["symbol"]), getattr(mt5, names[timeframe]), 0, max(10, min(int(p.get("count") or 220), 1000)))
        if rates is None:
            raise RuntimeError(f"Could not load candles: {mt5.last_error()}")
        return [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]), "close": float(r["close"]), "volume": int(r["tick_volume"])} for r in rates]

    def history(p):
        if mode == "simulation":
            return []
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, int(p.get("days") or 30)))
        deals = mt5.history_deals_get(start, end)
        if deals is None:
            raise RuntimeError(f"Could not read MT5 history: {mt5.last_error()}")
        groups = defaultdict(list)
        valid_types = {int(mt5.DEAL_TYPE_BUY), int(mt5.DEAL_TYPE_SELL)}
        for deal in deals:
            position_id = int(getattr(deal, "position_id", 0) or 0)
            if position_id and int(getattr(deal, "type", -1)) in valid_types:
                groups[position_id].append(deal)
        rows = []
        exits = {int(mt5.DEAL_ENTRY_OUT), int(mt5.DEAL_ENTRY_INOUT), int(getattr(mt5, "DEAL_ENTRY_OUT_BY", 3))}
        entries = {int(mt5.DEAL_ENTRY_IN), int(mt5.DEAL_ENTRY_INOUT)}
        for position_id, items in groups.items():
            items.sort(key=lambda deal: (int(getattr(deal, "time_msc", 0) or 0), int(deal.ticket)))
            opened = [deal for deal in items if int(getattr(deal, "entry", -1)) in entries]
            closed = [deal for deal in items if int(getattr(deal, "entry", -1)) in exits]
            if not opened or not closed:
                continue
            first, last = opened[0], closed[-1]
            profit = sum(float(getattr(deal, "profit", 0) or 0) for deal in items)
            swap = sum(float(getattr(deal, "swap", 0) or 0) for deal in items)
            commission = sum(float(getattr(deal, "commission", 0) or 0) + float(getattr(deal, "fee", 0) or 0) for deal in items)
            comments = [str(getattr(deal, "comment", "") or "") for deal in items]
            source = "Manual" if any(text.lower().startswith("koolkid manual") or text.startswith("KKM:") for text in comments) else next((text for text in comments if text), "MT5")
            rows.append({
                "id": position_id, "ticket": position_id, "account_login": int(config["login"]),
                "symbol": str(first.symbol), "type": "buy" if int(first.type) == int(mt5.DEAL_TYPE_BUY) else "sell",
                "volume": float(max(sum(float(deal.volume) for deal in opened), sum(float(deal.volume) for deal in closed))),
                "open_price": float(first.price), "close_price": float(last.price), "profit": profit,
                "swap": swap, "commission": commission, "net_pl": profit + swap + commission,
                "open_time": datetime.fromtimestamp(int(first.time), timezone.utc).isoformat(),
                "close_time": datetime.fromtimestamp(int(last.time), timezone.utc).isoformat(), "source": source,
            })
        rows.sort(key=lambda row: row["close_time"], reverse=True)
        return rows

    def require_trading_access():
        if read_only:
            raise RuntimeError("This MT5 account is connected with an investor password and is read-only.")

    def normalize_volume(volume, info):
        minimum = float(info.get("volume_min") or 0.01)
        maximum = float(info.get("volume_max") or max(volume, minimum))
        step = float(info.get("volume_step") or 0.01)
        value = max(minimum, min(float(volume), maximum))
        steps = int((value + 1e-12) / step)
        return round(max(minimum, min(steps * step, maximum)), 8)

    def margin_required(p):
        symbol = str(p["symbol"])
        side = str(p.get("side") or "buy").lower()
        volume = float(p.get("volume") or 0)
        if volume <= 0:
            raise RuntimeError("Volume must be greater than zero.")
        if mode == "simulation":
            return {"margin": max(0.01, volume) * 100.0, "volume": volume, "price": 100.0}
        info = symbol_info(symbol)
        if not info:
            raise RuntimeError(f"Symbol unavailable: {symbol}")
        volume = normalize_volume(volume, info)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {symbol}")
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if side == "buy" else tick.bid)
        margin = mt5.order_calc_margin(order_type, symbol, volume, price)
        if margin is None:
            raise RuntimeError(f"Could not calculate margin for {symbol}: {mt5.last_error()}")
        return {"margin": float(margin), "volume": volume, "price": price}

    def open_trade(p):
        nonlocal next_ticket
        require_trading_access()
        symbol = p["symbol"]
        side = p["side"]
        volume = float(p["volume"])
        sl = float(p.get("sl") or 0)
        tp = float(p.get("tp") or 0)
        magic = int(p.get("magic") or 0)
        comment = str(p.get("comment") or "KOOLKID")[:31]

        if mode == "simulation":
            next_ticket += 1
            sim_positions[next_ticket] = {
                "ticket": next_ticket, "symbol": symbol,
                "type": 0 if side == "buy" else 1,
                "side": side, "volume": volume,
                "price_open": 100.0, "price_current": 100.0,
                "sl": sl, "tp": tp, "profit": 0.0,
                "magic": magic, "comment": comment, "time": int(time.time()),
            }
            return {"ticket": next_ticket, "retcode": 10009}

        info = symbol_info(symbol)
        if not info:
            raise RuntimeError(f"Symbol unavailable: {symbol}")
        volume = normalize_volume(volume, info)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {symbol}")
        order_type = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
        price = float(tick.ask if side == "buy" else tick.bid)
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
            "type": order_type, "price": price, "sl": sl, "tp": tp,
            "deviation": 20, "magic": magic, "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        worker_received_at = time.time()
        out = send_market_order(mt5, req, info)
        ticket = int(out.get("order") or out.get("deal") or 0)
        # Resolve a live position ticket when possible.
        for _ in range(4):
            tagged = [x for x in positions() if x.get("symbol") == symbol and str(x.get("comment") or "").startswith(comment[:16])]
            if tagged:
                ticket = int(tagged[-1].get("ticket") or ticket)
                break
            time.sleep(0.025)
        out["ticket"] = ticket
        out.setdefault("timing", {})["worker_received_at"] = worker_received_at
        out["timing"]["position_confirmed_at"] = time.time()
        return out

    def close_position(p):
        require_trading_access()
        ticket = int(p["ticket"])
        if mode == "simulation":
            if ticket not in sim_positions:
                raise RuntimeError(f"Position {ticket} not found")
            sim_positions.pop(ticket, None)
            return {"ticket": ticket, "closed": True}

        found = mt5.positions_get(ticket=ticket) or []
        if not found:
            raise RuntimeError(f"Position {ticket} not found")
        pos = found[0]
        tick = mt5.symbol_info_tick(pos.symbol)
        buy_pos = int(pos.type) == int(mt5.POSITION_TYPE_BUY)
        info = symbol_info(pos.symbol)
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": pos.symbol,
            "volume": float(pos.volume),
            "type": mt5.ORDER_TYPE_SELL if buy_pos else mt5.ORDER_TYPE_BUY,
            "price": float(tick.bid if buy_pos else tick.ask),
            "deviation": 20, "magic": 0, "comment": "KOOLKID close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        worker_received_at = time.time()
        out = send_market_order(mt5, req, info)
        out.setdefault("timing", {})["worker_received_at"] = worker_received_at
        out["timing"]["position_confirmed_at"] = time.time()
        return out

    def close_partial(p):
        require_trading_access()
        ticket = int(p["ticket"])
        requested = float(p.get("volume") or 0)
        if requested <= 0:
            raise RuntimeError("Partial-close volume must be greater than zero.")
        if mode == "simulation":
            pos = sim_positions.get(ticket)
            if not pos:
                raise RuntimeError(f"Position {ticket} not found")
            current = float(pos.get("volume") or 0)
            if requested >= current:
                raise RuntimeError("Partial-close volume must be smaller than the open position.")
            pos["volume"] = round(current - requested, 8)
            return {"ticket": ticket, "closed_volume": requested, "remaining_volume": pos["volume"], "partial": True}

        found = mt5.positions_get(ticket=ticket) or []
        if not found:
            raise RuntimeError(f"Position {ticket} not found")
        pos = found[0]
        info = symbol_info(pos.symbol)
        if not info:
            raise RuntimeError(f"Symbol unavailable: {pos.symbol}")
        volume = normalize_volume(requested, info)
        if volume <= 0 or volume >= float(pos.volume):
            raise RuntimeError("Partial-close volume must be smaller than the open position after broker volume normalization.")
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            raise RuntimeError(f"No tick for {pos.symbol}")
        buy_pos = int(pos.type) == int(mt5.POSITION_TYPE_BUY)
        req = {
            "action": mt5.TRADE_ACTION_DEAL, "position": ticket, "symbol": pos.symbol,
            "volume": volume, "type": mt5.ORDER_TYPE_SELL if buy_pos else mt5.ORDER_TYPE_BUY,
            "price": float(tick.bid if buy_pos else tick.ask), "deviation": 20,
            "magic": int(getattr(pos, "magic", 0) or 0), "comment": "KOOLKID partial",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        out = send_market_order(mt5, req, info)
        out["closed_volume"] = volume
        out["partial"] = True
        return out

    def modify_position(p):
        require_trading_access()
        ticket = int(p["ticket"])
        sl = float(p.get("sl") or 0)
        tp = float(p.get("tp") or 0)
        if mode == "simulation":
            pos = sim_positions.get(ticket)
            if not pos:
                raise RuntimeError(f"Position {ticket} not found")
            pos["sl"], pos["tp"] = sl, tp
            return {"ticket": ticket, "modified": True}
        found = mt5.positions_get(ticket=ticket) or []
        if not found:
            raise RuntimeError(f"Position {ticket} not found")
        pos = found[0]
        out = plain(mt5.order_send({
            "action": mt5.TRADE_ACTION_SLTP, "position": ticket,
            "symbol": pos.symbol, "sl": sl, "tp": tp
        }))
        if int(out.get("retcode", -1)) not in {10008,10009,10010}:
            raise RuntimeError(f"Modify rejected: {out}")
        return out

    ops = {
        "account_info": lambda p: account_info(),
        "positions": lambda p: positions(),
        "symbol_info": lambda p: symbol_info(p["symbol"]),
        "symbols": symbol_catalog,
        "quotes": quotes,
        "candles": candles,
        "history": history,
        "margin_required": margin_required,
        "open_trade": open_trade,
        "close_position": close_position,
        "close_partial": close_partial,
        "modify_position": modify_position,
    }

    while True:
        try:
            cmd = command_q.get(timeout=0.5)
        except queue.Empty:
            continue
        rid, op, payload = cmd["id"], cmd["op"], cmd.get("payload") or {}
        try:
            if op == "shutdown":
                response_q.put({"id": rid, "ok": True, "result": {"stopped": True}})
                break
            if op not in ops:
                raise RuntimeError(f"Unknown operation: {op}")
            response_q.put({"id": rid, "ok": True, "result": ops[op](payload)})
        except Exception as exc:
            response_q.put({"id": rid, "ok": False, "error": str(exc), "trace": traceback.format_exc(limit=2)})

    if mt5 is not None:
        try: mt5.shutdown()
        except Exception: pass
