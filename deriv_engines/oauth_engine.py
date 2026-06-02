import json

from .barrier_resolver import sanitize_parameters
from .contract_resolver import contracts_for_candidates, normalize_contract_type
from .symbol_resolver import resolve_symbol
from .unchain_barrier import sanitize_unchain_higher_lower_barrier


class OAuthDerivTradeEngine:
    """Proposal-first Deriv Options engine for OAuth OTP WebSocket users only."""

    def __init__(self, deps):
        self.deps = deps

    def execute(self, intent, *, state):
        d = self.deps
        client_id = intent.client_id
        req_id = intent.req_id
        mode = d["connection_mode"](state)
        account_type = "demo" if d["is_demo"]({"account_id": state.get("deriv_account_id")}) else "real"
        debug = {
            "button": intent.button or intent.strategy_name,
            "profile": intent.profile,
            "connection_mode": mode,
            "account_id": state.get("deriv_account_id"),
            "account_type": account_type,
            "ws_ready_state": d["ws_ready_state"](state),
            "otp_authenticated": d["otp_authenticated"](state),
            "requested_symbol": intent.symbol,
            "requested_contract_type": intent.contract_type,
            "requested_barrier": intent.barrier,
        }
        d["logger"].info(
            "[%s] oauth_engine_trade_start profile=%s button=%s connection_mode=%s account_id=%s account_type=%s",
            client_id,
            intent.profile,
            intent.button or intent.strategy_name or intent.mode or "",
            mode,
            d["mask_account"](state.get("deriv_account_id") or ""),
            account_type,
        )

        active_symbols, active_err = d["active_symbols"](client_id, state)
        if active_err:
            return self._fail("symbol_resolver", active_err, client_id, debug, state)
        resolved_symbol, symbol_err = resolve_symbol(active_symbols, intent.symbol, d.get("legacy_aliases") or {})
        debug["underlying_symbol"] = resolved_symbol
        if symbol_err:
            d["logger"].info("[%s] skipped_invalid_symbol=%s context=%s error=%s", client_id, intent.symbol, intent.button or intent.profile or "trade", symbol_err)
            return self._fail("symbol_resolver", symbol_err, client_id, debug, state)

        deriv_contract = normalize_contract_type(intent.contract_type)
        debug["deriv_contract_type"] = deriv_contract
        if not deriv_contract:
            return self._fail("contract_resolver", "Invalid contract type", client_id, debug, state)
        contracts_for, contracts_err = d["contracts_for"](client_id, state, resolved_symbol)
        if contracts_err:
            return self._fail("contracts_for_error", contracts_err, client_id, debug, state)
        available = bool(contracts_for_candidates(contracts_for, deriv_contract))
        debug["contract_available"] = available
        if not available:
            return self._fail("contract_resolver", f"Contract type {deriv_contract} is not available for {resolved_symbol}", client_id, debug, state)

        parameters = {
            "amount": float(intent.stake),
            "basis": "stake",
            "contract_type": deriv_contract,
            "currency": intent.currency or "USD",
            "duration": int(intent.duration),
            "duration_unit": intent.duration_unit,
            "symbol": resolved_symbol,
        }
        if intent.barrier not in (None, ""):
            parameters["barrier"] = intent.barrier
        if intent.barrier2 not in (None, ""):
            parameters["barrier2"] = intent.barrier2
        if deriv_contract.startswith("DIGIT") and intent.barrier not in (None, ""):
            try:
                parameters["barrier"] = int(float(intent.barrier))
            except Exception:
                parameters["barrier"] = str(intent.barrier)

        sanitized, sanitize_err, sanitize_meta = sanitize_parameters(
            parameters,
            contracts_for=contracts_for,
            contract_type=deriv_contract,
            requested_barrier=intent.barrier,
            duration=intent.duration,
            duration_unit=intent.duration_unit,
            duration_matcher=d.get("duration_matches"),
        )
        debug["original_payload"] = parameters
        debug["sanitized_payload"] = sanitized
        debug["resolved_barrier"] = (sanitize_meta or {}).get("resolved_barrier")
        debug["matched_contract"] = (sanitize_meta or {}).get("matched_item")
        removed = (sanitize_meta or {}).get("removed") or {}
        if removed:
            debug["removed_fields"] = ",".join(sorted(removed.keys()))
        d["logger"].info(
            "[%s] oauth_engine_parameters_sanitized original_parameters=%s sanitized_parameters=%s removed_fields=%s resolved_barrier=%s matched_contract=%s",
            client_id,
            d["safe_payload"](parameters),
            d["safe_payload"](sanitized),
            ",".join(sorted(removed.keys())),
            debug.get("resolved_barrier"),
            d["safe_payload"](debug.get("matched_contract") or {}),
        )
        if sanitize_err:
            return self._fail("parameter_sanitizer", sanitize_err, client_id, debug, state)
        is_unchain_higher_lower = str(intent.profile or "").upper().strip() == "UNCHAIN" and deriv_contract in ("CALL", "PUT")
        if is_unchain_higher_lower:
            before_unchain = dict(sanitized)
            sanitized["barrier"] = sanitize_unchain_higher_lower_barrier(
                sanitized.get("barrier", intent.barrier),
                deriv_contract,
            )
            removed_barrier2 = None
            if "barrier2" in sanitized:
                removed_barrier2 = sanitized.pop("barrier2", None)
            debug["sanitized_payload"] = sanitized
            debug["resolved_barrier"] = sanitized.get("barrier")
            d["logger"].info(
                "[%s] unchain_oauth_barrier_finalized selected_market=%s contract_type=%s duration=%s duration_unit=%s original_parameters=%s final_parameters=%s removed_barrier2=%s",
                client_id,
                resolved_symbol,
                deriv_contract,
                intent.duration,
                intent.duration_unit,
                d["safe_payload"](before_unchain),
                d["safe_payload"](sanitized),
                removed_barrier2 is not None,
            )

        req_meta = dict(intent.req_meta or {})
        req_meta.setdefault("profile", intent.profile or state.get("active_profile"))
        req_meta.setdefault("type", intent.contract_type)
        req_meta.setdefault("contract_type", intent.contract_type)
        req_meta.setdefault("deriv_contract_type", deriv_contract)
        req_meta["requested_barrier"] = intent.barrier
        req_meta["barrier"] = sanitized.get("barrier")
        req_meta["resolved_barrier"] = sanitized.get("barrier")
        req_meta.setdefault("stake", float(intent.stake))
        req_meta.setdefault("symbol", intent.symbol)
        req_meta.setdefault("underlying_symbol", resolved_symbol)
        req_meta.setdefault("time", d["now_time"]())
        req_meta.setdefault("mode", intent.mode)
        req_meta.setdefault("duration", int(intent.duration))
        req_meta.setdefault("duration_unit", intent.duration_unit)
        if intent.budget_reservation is not None:
            req_meta.setdefault("budget_reservation", intent.budget_reservation)
        state.setdefault("req_meta", {})[req_id] = req_meta
        d["stamp_latency"](req_meta, "buy_send")

        proposal = None
        proposal_err = None
        min_profit = None
        try:
            min_profit = float(intent.minimum_profit) if intent.minimum_profit not in (None, "") else None
        except Exception:
            min_profit = None
        max_attempts = max(1, min(8, 1 + int(intent.minimum_profit_retries or 0)))
        best_proposal = None
        best_profit = None
        best_req_id = None
        for attempt in range(max_attempts):
            proposal_req_id = req_id if attempt == 0 else d["new_req_id"]()
            if proposal_req_id != req_id:
                state.setdefault("req_meta", {})[proposal_req_id] = req_meta
            proposal_payload = d["proposal_payload_for_connection"](state, {"proposal": 1, "req_id": proposal_req_id, **sanitized})
            debug["proposal_payload"] = proposal_payload
            debug["proposal_attempt"] = attempt + 1
            d["debug_log"](client_id, "oauth_proposal_send", debug)
            proposal, proposal_err = d["request_proposal"](client_id, state, proposal_payload, timeout_sec=5.0)
            debug["proposal_response"] = proposal or {"error": proposal_err}
            debug["proposal_id"] = (proposal or {}).get("id")
            if proposal_err:
                break
            if min_profit is None:
                break
            ask_price = d["safe_float"]((proposal or {}).get("ask_price"), d["safe_float"]((proposal or {}).get("display_value"), intent.stake))
            payout = d["safe_float"]((proposal or {}).get("payout"), None)
            profit = d["safe_float"]((proposal or {}).get("profit"), None)
            if profit is None and ask_price is not None and payout is not None:
                profit = float(payout) - float(ask_price)
            debug["proposal_profit"] = profit
            debug["minimum_profit"] = min_profit
            if profit is not None and float(profit) + 1e-9 >= float(min_profit):
                req_id = proposal_req_id
                break
            if profit is not None and (best_profit is None or float(profit) > float(best_profit)):
                if best_req_id not in (None, proposal_req_id):
                    try:
                        state.get("req_meta", {}).pop(best_req_id, None)
                    except Exception:
                        pass
                best_proposal = proposal
                best_profit = profit
                best_req_id = proposal_req_id
            elif proposal_req_id != req_id:
                try:
                    state.get("req_meta", {}).pop(proposal_req_id, None)
                except Exception:
                    pass
            if attempt >= max_attempts - 1:
                if intent.buy_best_available and best_proposal:
                    proposal = best_proposal
                    req_id = best_req_id or req_id
                    d["logger"].info(
                        "[%s] oauth_matches_frenzy_best_available selected_profit=%s target_profit=%s proposal=%s",
                        client_id,
                        None if best_profit is None else round(float(best_profit), 4),
                        round(float(min_profit), 4),
                        d["safe_payload"](best_proposal or {}),
                    )
                    break
                try:
                    state.get("req_meta", {}).pop(proposal_req_id, None)
                except Exception:
                    pass
                msg = f"Matches Frenzy skipped: proposal profit {float(profit or 0.0):.2f} below target {float(min_profit):.2f}"
                return self._fail("minimum_profit_filter", msg, client_id, debug, state, cleanup=False)
            try:
                state.get("req_meta", {}).pop(proposal_req_id, None)
            except Exception:
                pass
        if proposal_err:
            if is_unchain_higher_lower:
                d["logger"].warning(
                    "[%s] unchain_oauth_proposal_rejected selected_market=%s contract_type=%s duration=%s duration_unit=%s barrier=%s proposal_payload=%s deriv_error=%s websocket_stayed_connected=%s",
                    client_id,
                    resolved_symbol,
                    deriv_contract,
                    intent.duration,
                    intent.duration_unit,
                    sanitized.get("barrier"),
                    d["safe_payload"](debug.get("proposal_payload") or {}),
                    proposal_err,
                    bool(state.get("ws_connected")),
                )
            try:
                state.get("req_meta", {}).pop(req_id, None)
            except Exception:
                pass
            return self._fail("proposal_response", proposal_err, client_id, debug, state, cleanup=False)
        proposal_id = (proposal or {}).get("id")
        if proposal_id in (None, ""):
            try:
                state.get("req_meta", {}).pop(req_id, None)
            except Exception:
                pass
            return self._fail("proposal_id_missing", "Proposal id missing", client_id, debug, state, cleanup=False)
        ask_price = d["safe_float"]((proposal or {}).get("ask_price"), d["safe_float"]((proposal or {}).get("display_value"), intent.stake))
        buy_payload = {"req_id": req_id, "buy": proposal_id, "price": float(ask_price if ask_price is not None else intent.stake)}
        debug["buy_payload"] = buy_payload
        d["debug_log"](client_id, "oauth_buy_send", debug)
        try:
            state.get("ws").send(json.dumps(buy_payload))
        except Exception as exc:
            try:
                state.get("req_meta", {}).pop(req_id, None)
            except Exception:
                pass
            debug["error"] = str(exc)
            debug["failed_at"] = "buy_send"
            d["debug_log"](client_id, "oauth_buy_failed", debug)
            should_reconnect = True
            try:
                should_reconnect = bool(d.get("should_force_reconnect", lambda _state, _exc: True)(state, exc))
            except Exception:
                should_reconnect = True
            if should_reconnect:
                d["mark_ws_unhealthy"](client_id, state, "Deriv connection failed while sending a trade. Reconnecting now...")
            else:
                d["logger"].warning(
                    "[%s] trade_failed_without_disconnect=true failed_at=buy_send error=%s ws_ready_state=%s otp_authenticated=%s",
                    client_id,
                    exc,
                    d["ws_ready_state"](state),
                    d["otp_authenticated"](state),
                )
            return False, str(exc)
        d["logger"].info("[%s] oauth_engine_trade_sent proposal_id=%s buy_payload=%s", client_id, proposal_id, d["safe_payload"](buy_payload))
        return True, "Trade sent"

    def _fail(self, failed_at, message, client_id, debug, state, cleanup=True):
        debug["error"] = message
        debug["failed_at"] = failed_at
        self.deps["debug_log"](client_id, "oauth_blocked", debug)
        self.deps["logger"].info(
            "[%s] trade_failed_without_disconnect=true failed_at=%s ws_ready_state=%s otp_authenticated=%s",
            client_id,
            failed_at,
            self.deps["ws_ready_state"](state),
            self.deps["otp_authenticated"](state),
        )
        return False, message
