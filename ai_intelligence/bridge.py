"""Adapters to existing bot functions. No credentials leave the runtime."""
import json
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from flask import session

from deriv_engines.contract_resolver import CONTRACT_ALIASES, contracts_for_candidates
from deriv_engines.symbol_resolver import resolve_symbol
from deriv_engines.unchain_barrier import choose_unchain_contract, validate_unchain_higher_lower_barrier
from human_profile_contracts import HUMAN_MANUAL_ACTIONS, build_human_manual_contract_info
from .commands import CommandError, number, redact


class Host:
    def __init__(self, namespace):
        self.namespace = namespace

    def __getattr__(self, key):
        return self.namespace[key]


def binding(state):
    return (state.get("username"), state.get("options_account_id") or state.get("deriv_account_id"),
            state.get("loginid"), state.get("ws_nonce"), id(state.get("ws")))


def hub(state):
    return state.setdefault("_ai_intelligence", SimpleNamespace(
        lock=threading.Lock(), plans={}, messages=[], previous=None, account=None,
        csrf=secrets.token_urlsafe(32), stopped=False, generation=0, last_command=0.0, receipts={}, clarification=None))


def observe_response(state, data):
    """Observe only AI buy acknowledgements; leave existing settlement handling intact."""
    ai = state.get("_ai_intelligence")
    if not ai:
        return
    rid = data.get("req_id") or (data.get("echo_req") or {}).get("req_id")
    receipt = ai.receipts.get(str(rid))
    if receipt is None:
        return
    if isinstance(data.get("buy"), dict) and data["buy"].get("contract_id"):
        receipt["result"] = {"status": "confirmed", "contract_id": str(data["buy"]["contract_id"])}
        receipt["event"].set()
    elif data.get("error") and ((data.get("echo_req") or {}).get("buy") is not None or data.get("msg_type") == "buy"):
        receipt["result"] = {"status": "failed", "message": "Deriv rejected the buy. Check the bot's trade notification."}
        receipt["event"].set()


def check_buy(state, req_id):
    ai = state.get("_ai_intelligence")
    if ai and ai.stopped:
        return "AI emergency pause is active. Use 'Resume trading' before placing new orders."
    meta = (state.get("req_meta") or {}).get(req_id) or {}
    expected = meta.get("ai_binding")
    if expected is not None and (binding(state) != expected or meta.get("ai_generation") != ai.generation):
        return "Account or connection changed. This AI order was cancelled."
    return None


class Bridge:
    def __init__(self, app, namespace):
        self.app = app
        self.s = Host(namespace)
        self.schema_lock = threading.Lock()
        self.schema_ready = False

    def authorize(self):
        if not self.s.login_required():
            raise CommandError("Sign in to use AI Intelligence.")
        if not self.s.is_lifetime_feature_user():
            raise CommandError("AI Intelligence is available to Lifetime users only.")
        cid = self.s.get_client_id()
        state = self.s.clients.get(cid)
        if state and state.get("username") not in (None, session.get("user")):
            raise CommandError("This bot session belongs to a different user. Sign in again.")
        return self.s.get_client_state()

    def invoke(self, function, payload):
        # Call only a programmer-selected existing view, with its usual JSON/session contract.
        # No URL, function name, cookies, or identity can come from the model.
        identity = dict(session)
        with self.app.test_request_context("/ai-intelligence/internal", method="POST", json=payload):
            session.update(identity)
            response = self.app.make_response(function())
            data = response.get_json() or {}
        if response.status_code >= 400 or data.get("status") == "error":
            raise CommandError("The existing bot control rejected this action. Check its settings and connection.")
        return data

    def db(self, sql, params=(), fetch=False):
        with self.schema_lock:
            conn = self.s._db_connect()
            try:
                cur = conn.cursor()
                if not self.schema_ready:
                    self.s._db_execute(cur, "CREATE TABLE IF NOT EXISTS ai_intelligence_preferences (username TEXT PRIMARY KEY, visible INTEGER NOT NULL)")
                    self.s._db_execute(cur, "CREATE TABLE IF NOT EXISTS ai_intelligence_audit (id TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT NOT NULL, record TEXT NOT NULL)")
                self.s._db_execute(cur, sql, params)
                row = cur.fetchone() if fetch else None
                conn.commit()
                self.schema_ready = True
                return row
            finally:
                conn.close()

    def preference(self, visible=None):
        if visible is not None:
            self.db("INSERT INTO ai_intelligence_preferences (username, visible) VALUES (?, ?) ON CONFLICT(username) DO UPDATE SET visible=excluded.visible", (session["user"], int(visible)))
        row = self.db("SELECT visible FROM ai_intelligence_preferences WHERE username=?", (session["user"],), True)
        return bool(row[0]) if row else True

    def audit(self, action, result, record_id=None):
        # Store the canonical command rather than raw free text (which may contain secrets).
        safe_result = {key: result[key] for key in ("status", "message", "plan", "index", "trade_type", "market", "stake", "contract_id", "request_id") if key in result}
        record = {"command": action, "result": safe_result}
        self.db("INSERT INTO ai_intelligence_audit (id, username, created_at, record) VALUES (?, ?, ?, ?)",
                (record_id or secrets.token_hex(16), session["user"], datetime.now(timezone.utc).isoformat(), json.dumps(record)))

    def settings(self, state):
        profile = state.get("active_profile")
        strategy = state.get("strategies", {}).get(profile)
        ui_payload = {}
        if strategy and hasattr(strategy, "get_ui_payload"):
            try:
                ui_payload = strategy.get_ui_payload()
            except Exception:
                # Account information should remain available if a profile UI adapter is stale.
                ui_payload = {}
        return {"profile": profile, "market": (state.get("human_symbol") if profile == "HUMAN" else state.get("current_symbol")),
                "stake": state.get("auto_stake"), "connected": bool(state.get("ws_connected")),
                "account": self.s._mask_account_id(state.get("loginid") or ""),
                "account_type": "demo" if self.s._oauth_account_is_demo({"account_id": state.get("loginid")}) else "real",
                "balance": self.s._get_live_account_balance(state) if state.get("ws_connected") else None,
                "currency": self.currency(state), "emergency_paused": hub(state).stopped,
                "auto_trade": bool(getattr(strategy, "auto_trade", False)),
                "auto_modes": {key: value for key, value in (ui_payload.get("auto_modes") or {}).items() if type(value) is bool},
                "active_strategies": [name for name, st in (state.get("strategies") or {}).items()
                                      if getattr(st, "auto_trade", False) or any(v is True for k, v in vars(st).items() if k.endswith("_auto"))]}

    def diagnostics(self, state):
        now = time.time()
        last_message = float(state.get("ws_last_message_at", 0.0) or 0.0)
        health = self.s.martha_health_snapshot(state)
        return {
            "connected": bool(state.get("ws_connected") and state.get("ws")),
            "connection_type": str(state.get("api_token_type") or "unknown"),
            "reconnect_pending": bool(state.get("ws_reconnect_pending")),
            "reconnect_attempts": int(state.get("ws_reconnect_attempts", 0) or 0),
            "seconds_since_message": round(max(0.0, now - last_message), 1) if last_message else None,
            "proposal_waiters": len({id(row) for row in (state.get("_proposal_waiters") or {}).values() if isinstance(row, dict)}),
            "tracked_contracts": len(state.get("contract_meta") or {}),
            "martha": health,
        }

    @staticmethod
    def currency(state):
        account = state.get("options_account_id") or state.get("deriv_account_id") or state.get("loginid")
        for item in list(state.get("pat_accounts") or []) + list(state.get("oauth_pending_accounts") or []):
            if str(item.get("account_id")) == str(account) and item.get("currency"):
                return str(item["currency"])
        return str(state.get("currency") or "USD")

    def market(self, cid, state, value):
        if not isinstance(value, str) or not 1 <= len(value) <= 80:
            raise CommandError("Choose a valid market.")
        symbols, error = self.s._get_active_symbols_for_state(cid, state)
        if error:
            raise CommandError("Could not retrieve Deriv markets. Check the connection and try again.")
        key = re.sub(r"[^a-z0-9]", "", value.lower())
        for item in symbols:
            if key == re.sub(r"[^a-z0-9]", "", str(item.get("display_name") or "").lower()):
                return item.get("symbol") or item.get("underlying_symbol")
        m = re.fullmatch(r"(?:v|vol|volatility)(\d+)(?:index)?(1s)?", key)
        candidate = ("1HZ" + m[1] + "V" if m[2] else "R_" + m[1]) if m else value
        resolved, error = resolve_symbol(symbols, candidate, self.s._LEGACY_SYMBOL_ALIASES)
        if error:
            raise CommandError("That market is not in the connected account's available markets.")
        return resolved

    def profile(self, state, value):
        if not isinstance(value, str):
            raise CommandError("Which profile should I use?")
        p = value.upper().replace(" ", "")
        p = {"MUTANT": "NTT"}.get(p, p)
        if p == "KIDGX":
            return "KIDGX"
        if p not in state.get("strategies", {}):
            raise CommandError("Unknown profile.")
        return p

    def prepare(self, cid, state, plan):
        settings = self.settings(state)
        current_profile = settings["profile"]
        stake = settings["stake"]
        market = settings["market"]
        output = []
        total = 0.0
        for original in plan["actions"]:
            a = dict(original)
            name = a["action"]
            if "stake" in a or name in ("place_trade", "change_stake"):
                a["stake"] = number(a.get("stake", stake), "stake", 0.35, 1000000)
            if name == "change_stake":
                stake = a["stake"]
            if name in ("place_trade", "change_market"):
                if not state.get("ws_connected"):
                    raise CommandError("Connect a Deriv account first.")
                a["market"] = self.market(cid, state, a.get("market", market))
                if name == "change_market":
                    market = a["market"]
            if name in ("start_auto_strategy", "stop_auto_strategy", "switch_profile"):
                a["profile"] = self.profile(state, a.get("profile", current_profile))
                if a["profile"] == "CLOUD" and name == "start_auto_strategy":
                    raise CommandError("Start Cloud from its existing panel after verifying its separate session settings.")
                if a["profile"] == "NTT" and name == "start_auto_strategy":
                    raise CommandError("Start Mutant from its existing AUTO panel to confirm its budget, barrier and mode.")
                if name in ("start_auto_strategy", "switch_profile"):
                    current_profile = "JOKERJOE" if a["profile"] == "KIDGX" else a["profile"]
                if name == "start_auto_strategy" and not state.get("ws_connected"):
                    raise CommandError("Connect a Deriv account before starting AUTO.")
            if name in ("get_trade_history",):
                a["limit"] = int(number(a.get("limit", 5), "history limit", 1, 50))
            if name == "get_development_requests":
                a["limit"] = int(number(a.get("limit", 10), "request limit", 1, 25))
            if name == "submit_development_request":
                category = str(a.get("category") or "").strip().lower()
                summary = str(a.get("summary") or "").strip()
                if category not in ("bug", "feature") or not 5 <= len(summary) <= 1200:
                    raise CommandError("Development requests need a bug/feature category and a clear description.")
                a["category"] = category
                a["summary"] = redact(summary)
            if "today" in a and not isinstance(a["today"], bool):
                raise CommandError("Invalid statistics period.")
            if name == "change_barrier":
                a["barrier"] = self.digit(a.get("barrier"))
            if "martingale" in name:
                if current_profile not in ("HUMAN", "KOOLKID", "JOKERJOE", "UNCHAIN"):
                    raise CommandError("Use this profile's existing martingale panel; no generic martingale control is available.")
                if name == "set_martingale_multiplier":
                    if current_profile == "JOKERJOE":
                        raise CommandError("JokerJoe Match Batch has fixed doubling, not an adjustable multiplier.")
                    a["multiplier"] = number(a.get("multiplier"), "multiplier", 1, 100)
                a["ui_profile"] = current_profile
            if name == "place_trade":
                if self.currency(state) != "USD":
                    raise CommandError("AI trade execution currently supports the bot's USD accounts only. Use the existing trade controls for this account.")
                a["profile"] = current_profile
                a["current_stake_used"] = "stake" not in original
                a["duration"] = number(a.get("duration", 1), "duration", 1, 86400)
                if a["duration"] != int(a["duration"]):
                    raise CommandError("Duration must be a whole number.")
                a["duration"] = int(a["duration"])
                a["duration_unit"] = a.get("duration_unit", "t")
                if a["duration_unit"] not in ("t", "s", "m", "h", "d"):
                    raise CommandError("Unsupported duration unit.")
                raw = a.get("trade_type")
                special = raw.upper().replace(" ", "_") if isinstance(raw, str) else ""
                if not isinstance(raw, str) or (raw.upper() not in CONTRACT_ALIASES and special not in HUMAN_MANUAL_ACTIONS):
                    raise CommandError("Which supported trade type should I use?")
                a["trade_type"] = raw.upper()
                if special in HUMAN_MANUAL_ACTIONS:
                    contracts, error = self.s._get_contracts_for_symbol(cid, state, a["market"])
                    info = build_human_manual_contract_info((contracts or {}).get("available") or []).get(special) or {}
                    if error or not info.get("available"):
                        raise CommandError("This special contract is unavailable for this market.")
                    a["contract_type"] = info["contract_type"]
                    if "duration" not in original:
                        a["duration"] = info["default_duration"]
                    if "duration_unit" not in original:
                        a["duration_unit"] = info["duration_unit"]
                    if special in ("HIGH_TICK", "LOW_TICK"):
                        selected = number(a.get("selected_tick"), "selected tick", 1, 5)
                        if selected != int(selected):
                            raise CommandError("Selected tick must be a whole number.")
                        a["selected_tick"] = int(selected)
                else:
                    a["contract_type"] = CONTRACT_ALIASES[raw.upper()]
                    if "selected_tick" in a:
                        raise CommandError("Selected tick is only valid for High Tick and Low Tick.")
                ct = a["contract_type"]
                if ct in ("DIGITOVER", "DIGITUNDER", "DIGITMATCH", "DIGITDIFF"):
                    a["barrier"] = self.digit(a.get("barrier"))
                    if (ct == "DIGITOVER" and a["barrier"] == 9) or (ct == "DIGITUNDER" and a["barrier"] == 0):
                        raise CommandError("That barrier cannot win for this contract type.")
                elif raw.upper() in ("HIGHER", "LOWER", "TOUCH", "NO TOUCH", "NO_TOUCH", "NO-TOUCH"):
                    if not isinstance(a.get("barrier"), str) or not re.fullmatch(r"[+-](?:\d+(?:\.\d+)?|\.\d+)", a["barrier"]):
                        raise CommandError("What signed relative barrier should I use (for example +0.10 or -0.10)?")
                elif a.get("barrier") is not None:
                    raise CommandError("Rise/Fall and Even/Odd do not use a barrier.")
                self.contract(cid, state, a)
                total += a["stake"]
            output.append(a)
        if total and total > self.s._get_pre_trade_available_balance(state) + 1e-9:
            raise CommandError("Insufficient available balance for these trades.")
        return output

    @staticmethod
    def digit(value):
        n = number(value, "barrier digit", 0, 9)
        if n != int(n):
            raise CommandError("Barrier must be a whole digit from 0 to 9.")
        return int(n)

    def contract(self, cid, state, a):
        contracts, error = self.s._get_contracts_for_symbol(cid, state, a["market"])
        if error:
            raise CommandError("Could not verify this market's contracts. No order was placed.")
        candidates = [item for item in contracts_for_candidates(contracts, a["contract_type"])
                      if self.s._contract_item_duration_matches(item, a["duration"], a["duration_unit"])]
        if not candidates:
            raise CommandError("This contract or duration is unavailable for the selected market. Choose a supported duration.")
        if a["trade_type"] in ("HIGHER", "LOWER"):
            side = "up" if a["trade_type"] == "HIGHER" else "down"
            item, error = choose_unchain_contract(contracts, side, duration=a["duration"], duration_unit=a["duration_unit"], duration_matcher=self.s._contract_item_duration_matches)
            if error:
                raise CommandError("Higher/Lower is unavailable for this duration and market.")
            barrier, error = validate_unchain_higher_lower_barrier(a["barrier"], side, item)
            if error:
                raise CommandError("The signed barrier is not supported for this Higher/Lower contract.")
            a["barrier"] = barrier
        if a["trade_type"] in ("RISE", "FALL") and not any(self.s._contract_item_allows_no_barrier(i) for i in candidates):
            raise CommandError("Plain Rise/Fall is unavailable for this duration.")
        return contracts

    def trade(self, cid, state, a, expected, generation):
        self.authorize()
        ai = hub(state)
        if binding(state) != expected or ai.generation != generation or ai.stopped:
            raise CommandError("Account, connection, or stop state changed. Order cancelled.")
        ready, _ = self.s._ensure_trade_socket_ready(cid, state)
        if not ready:
            raise CommandError("Deriv is not ready for trading.")
        if a["stake"] > self.s._get_pre_trade_available_balance(state) + 1e-9:
            raise CommandError("Insufficient available balance.")
        strategy = state["strategies"].get(a["profile"])
        if strategy and hasattr(strategy, "enforce_tp_sl"):
            strategy.enforce_tp_sl()
            if getattr(strategy, "risk_block_reason", None):
                raise CommandError("The profile's TP/SL limit blocks this trade.")
        self.contract(cid, state, a)
        ok, _, reservation = self.s._reserve_profile_budget(state, a["profile"], a["stake"])
        if not ok:
            raise CommandError("This trade exceeds the profile's available budget.")
        rid = self.s._new_req_id()
        while rid in state.get("req_meta", {}) or str(rid) in ai.receipts:
            rid = self.s._new_req_id()
        meta = {"profile": a["profile"], "type": a["trade_type"], "stake": a["stake"], "symbol": a["market"],
                "barrier": a.get("barrier"), "duration": a["duration"], "duration_unit": a["duration_unit"],
                "deriv_contract_type": a["contract_type"], "time": self.s.now_time(), "mode": "AI_INTELLIGENCE",
                "budget_reservation": reservation, "ai_binding": expected, "ai_generation": generation}
        state.setdefault("req_meta", {})[rid] = meta
        payload = {"proposal": 1, "req_id": rid, "amount": a["stake"], "basis": "stake", "currency": "USD",
                   "contract_type": a["contract_type"], "duration": a["duration"], "duration_unit": a["duration_unit"], "symbol": a["market"]}
        if a.get("barrier") is not None:
            payload["barrier"] = str(a["barrier"])
        if a.get("selected_tick") is not None:
            payload["selected_tick"] = a["selected_tick"]
            meta["selected_tick"] = a["selected_tick"]
        payload = self.s._proposal_payload_for_connection(state, payload)
        sent = False
        receipt = {"event": threading.Event(), "result": None, "created": time.time()}
        ai.receipts = {key: value for key, value in ai.receipts.items() if value["created"] > time.time() - 3600}
        ai.receipts[str(rid)] = receipt
        try:
            quote, error = self.s._request_digit_proposal_for_buy(cid, state, payload, timeout_sec=5)
            if error or not quote or not quote.get("id"):
                raise CommandError("Deriv could not quote this trade. Verify its barrier, duration and market; try again later if rate limited.")
            self.authorize()
            error = check_buy(state, rid)
            if error:
                raise CommandError(error)
            ask = number(quote.get("ask_price", a["stake"]), "proposal price", 0.01, a["stake"])
            quote = dict(quote, ask_price=ask)
            # Never retry an uncertain buy. The existing reader still tracks its final result.
            receipt["sent"] = True
            sent = True
            with self.s._get_ws_lifecycle_lock(state):
                self.authorize()
                error = check_buy(state, rid)
                if error:
                    sent = False
                    raise CommandError(error)
                ok, _ = self.s._send_buy_from_proposal(cid, state, rid, quote, a["stake"])
            if not ok:
                sent = False
                raise CommandError("Purchase was blocked before submission.")
            receipt["event"].wait(8)
            result = receipt["result"] or {"status": "pending", "message": "Buy acknowledgement not received. Check trade history; this order will not be retried."}
            return {**result, "trade_type": a["trade_type"], "market": a["market"], "stake": a["stake"], "request_id": rid}
        finally:
            if not sent:
                state.get("req_meta", {}).pop(rid, None)
                self.s._release_profile_budget_reservation(state, reservation)

    def stop(self, cid, state, profile=None):
        ai = hub(state)
        ai.generation += 1
        if profile is None:
            ai.stopped = True
        ai.clarification = None
        targets = [profile] if profile else list(state.get("strategies", {}))
        for name in targets:
            strat = state.get("strategies", {}).get(name)
            if strat and hasattr(strat, "disable_all_autos"):
                strat.disable_all_autos()
            elif strat and hasattr(strat, "auto_trade"):
                strat.auto_trade = False
            if strat:
                # Some existing disable_all_autos implementations omit independent modes.
                # Disable only boolean execution flags, never risk/auto-SL configuration.
                for key, value in vars(strat).copy().items():
                    if type(value) is bool and (key.endswith("_auto") or key in ("auto_kidracks", "auto_koolspeed")):
                        setattr(strat, key, False)
                if hasattr(strat, "get_named_ai_modes_state"):
                    for key, enabled in strat.get_named_ai_modes_state().items():
                        if enabled:
                            strat.toggle_named_ai_mode(key)
            if name in ("KOOLKID", "JOKERJOE"):
                self.s.stop_seqvix(state, cid, name, reason="AI Intelligence stop")
            if name == "KOOLKID" and hasattr(strat, "stop_golden_card_scan"):
                strat.stop_golden_card_scan()
            if name == "HUMAN" and strat:
                strat.rf_auto_assist = False
            if name in ("NTT", "UNCHAIN"):
                runtime = self.s._ensure_ntt_state(state) if name == "NTT" else self.s._ensure_unchain_hl_state(state)
                for key in ("auto_both_enabled", "ai_auto_trade_enabled", "directional_auto_enabled", "primordial_blue_enabled", "hybrid_enabled", "koolkid_hl_enabled", "koolkid_both_enabled"):
                    if key in runtime:
                        runtime[key] = False
                if name == "NTT":
                    self.s.stop_mutant_auto(runtime, "AI Intelligence stop")
            if name == "CLOUD":
                key = self.s._cloud_key_for_state(state)
                if key:
                    self.s.cloud_manager.stop(key, "AI Intelligence stop")
                    self.s._stop_cloud_runtime_for_key(key, "ai_stop")
        if profile is None:
            self.s.stop_auto_session(state, "AI Intelligence stop")
        self.s.socketio.emit("ai_intelligence_stop", {"profile": profile}, room=cid)
        self.s.send_stats_update(cid)
        return {"status": "completed", "message": "Automated trading stopped. Purchased contracts were not sold." + (" New orders are paused until you say 'Resume trading'." if profile is None else ""), "stop_profile": profile, "settings": self.settings(state)}

    def read(self, state, a):
        settings = self.settings(state)
        name = a["action"]
        if name == "get_balance":
            return {"status": "completed", "message": f"Balance: {settings['balance']} {settings['currency']}." if settings["connected"] and settings["balance"] is not None else "Connect your account to retrieve its balance."}
        if name == "get_current_market":
            return {"status": "completed", "message": f"Current market: {settings['market']}."}
        if name in ("get_account_information", "get_current_settings"):
            return {"status": "completed", "data": settings, "message": json.dumps(settings, indent=2)}
        if name == "get_connection_health":
            data = self.diagnostics(state)
            status = "connected" if data["connected"] else ("reconnecting" if data["reconnect_pending"] else "disconnected")
            age = "unknown" if data["seconds_since_message"] is None else f"{data['seconds_since_message']} seconds ago"
            return {"status": "completed", "data": data, "message": f"Deriv is {status}. Last WebSocket message: {age}. Pending proposal requests: {data['proposal_waiters']}. Tracked contracts: {data['tracked_contracts']}."}
        if name == "get_martha_health":
            data = self.diagnostics(state)["martha"]
            issue = data.get("last_issue") or "none"
            action = data.get("last_action") or "none"
            return {"status": "completed", "data": data, "message": f"Martha health: {data.get('status')}. Consecutive failures: {data.get('consecutive_failures')}/{data.get('max_failures')}. Last issue: {issue}. Last recovery: {action}."}
        if name == "get_development_requests":
            rows = self.intelligence_store.development_requests(session["user"], a.get("limit", 10))
            if not rows:
                return {"status": "completed", "requests": [], "message": "You have no saved Martha development requests."}
            lines = [f"{row['id'][:8]} · {row['category'].upper()} · {row['status'].upper()} · {row['summary']}" for row in rows]
            return {"status": "completed", "requests": rows, "message": "Your Martha development requests:\n" + "\n".join(lines)}
        if name == "get_research_status":
            return {"status": "completed", "message": "Live internet research is not configured. Martha can use the OpenAI language provider when credits are available, but it will not claim current web research without a separate trusted search connector.", "data": {"connected": False, "provider": None}}
        profiles = self.s._get_profile_trade_history_snapshot(state)
        history = {row["contract_id"]: row for rows in profiles.values() for row in rows}
        rows = sorted(history.values(), key=lambda r: r.get("_sort_ts", 0), reverse=True)
        scope = "Available bot-session history only; not a complete account statement."
        if a.get("today"):
            start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            rows = [r for r in rows if r.get("_sort_ts", 0) >= start]
            scope = "Today's timestamped bot-session trades (UTC); entries without a date are excluded."
        if name == "get_trade_history":
            return {"status": "completed", "message": scope, "trades": rows[:a.get("limit", 5)]}
        wins = sum(r.get("profit", 0) > 0 for r in rows)
        losses = sum(r.get("profit", 0) < 0 for r in rows)
        rate = round(wins / (wins + losses) * 100, 2) if wins + losses else None
        return {"status": "completed", "message": f"{wins} wins, {losses} losses. Win rate: {rate if rate is not None else 'unavailable'}%. {scope}", "wins": wins, "losses": losses, "win_rate": rate}

    def control(self, cid, state, a):
        name = a["action"]
        if name == "stop_all_trading":
            return self.stop(cid, state)
        if name == "resume_trading":
            hub(state).stopped = False
            return {"status": "completed", "message": "New orders are allowed. No strategies were automatically restarted."}
        if name == "run_safe_recovery":
            if not (state.get("martha_ai") or {}).get("enabled"):
                raise CommandError("Turn Martha AI ON before running its safe recovery checks.")
            self.s._run_websocket_health_check(cid, state)
            result = self.s._run_martha_self_heal_check(cid, state)
            actions = list(result.get("actions") or [])
            message = "Safe recovery completed. " + ("Actions: " + ", ".join(actions) + "." if actions else "No stale state required repair.")
            return {"status": "completed", "message": message, "data": self.diagnostics(state)}
        if name == "submit_development_request":
            request_id = self.intelligence_store.create_development_request(
                session["user"], a["category"], a["summary"],
                {"profile": state.get("active_profile"), "diagnostics": self.diagnostics(state)},
            )
            return {"status": "completed", "request_id": request_id, "message": f"Saved {a['category']} request {request_id[:8]} for developer review. No code or live trading behavior was changed."}
        if name == "stop_auto_strategy":
            return self.stop(cid, state, "JOKERJOE" if a["profile"] == "KIDGX" else a["profile"])
        if name == "change_stake":
            self.invoke(self.s.set_auto_stake, {"stake": a["stake"]})
        elif name == "change_market":
            self.invoke(self.s.change_human_market if state["active_profile"] == "HUMAN" else self.s.change_market, {"symbol": a["market"]})
        elif name == "change_barrier":
            strategy = state["strategies"].get(state["active_profile"])
            if not hasattr(strategy, "set_selected_barrier"):
                raise CommandError("This profile uses its own barrier controls. Specify a barrier in the trade command instead.")
            strategy.set_selected_barrier(a["barrier"])
        elif name in ("switch_profile", "start_auto_strategy"):
            p = "JOKERJOE" if a["profile"] == "KIDGX" else a["profile"]
            data = self.invoke(self.s.set_profile, {"profile": p})
            if name == "start_auto_strategy":
                if hub(state).stopped:
                    raise CommandError("Use 'Resume trading' before starting a strategy.")
                if a["profile"] == "KIDGX":
                    st = state["strategies"][p]
                    if not getattr(st, "kidgx_auto", False):
                        self.invoke(self.s.toggle_kidgx_auto_route, {})
                elif p == "UNCHAIN":
                    self.invoke(self.s.toggle_unchain_auto_route, {"enabled": True})
                elif p == "NTT":
                    raise CommandError("Use Mutant's existing AUTO panel to confirm its budget, barrier and mode first.")
                elif not getattr(state["strategies"][p], "auto_trade", False):
                    self.invoke(self.s.toggle_auto, {})
            return {"status": "completed", "message": f"{p}: {'Master AUTO enabled' if name == 'start_auto_strategy' else 'profile selected'}.", "profile_data": data, "settings": self.settings(state)}
        elif "martingale" in name:
            return {"status": "ui_pending", "message": "Waiting for the existing martingale control.", "ui_action": a}
        self.s.emit_profile_snapshot(cid)
        return {"status": "completed", "message": "Setting updated.", "settings": self.settings(state), "control": a}
