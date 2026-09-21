from __future__ import annotations
import threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed

COPY_MAGIC = 987654

COPY_PREFERENCE_DEFAULTS = {
    "lot_mode": "same",
    "fixed_lot": 0.01,
    "multiplier": 1.0,
    "trail_by_shoulders": False,
    "risk_reward_ratio": 2.0,
    "shoulder_timeframe": "M5",
    "shoulder_strength": 2,
    "shoulder_buffer_points": 5.0,
    "limit_copied_trades": False,
    "max_copied_trades_per_slave": 1,
}


class CopyEngine:
    def __init__(self, pool, state):
        self.pool = pool
        self.state_store = state
        self.thread = None
        self.stop_event = threading.Event()
        saved_state = self.state_store.load()
        self.config = saved_state.get("copy_config")
        saved_preferences = dict(saved_state.get("copy_preferences") or {})
        if self.config:
            for key in COPY_PREFERENCE_DEFAULTS:
                if key in self.config and key not in saved_preferences:
                    saved_preferences[key] = self.config[key]
        self.preferences = {**COPY_PREFERENCE_DEFAULTS, **saved_preferences}
        self.status = "stopped"
        self.activity = []
        self.copy_map = saved_state.get("copy_map", {})
        self.pending = {}
        self.ignored = set()
        self.lock = threading.RLock()
        self.pause_until = 0.0

    def pause_for_execution(self, seconds=20):
        self.pause_until = max(self.pause_until, time.time() + max(1, seconds))

    def resume_after_execution(self):
        self.pause_until = time.time()

    def log(self, event, **extra):
        self.activity.insert(0, {"time": time.time(), "event": event, **extra})
        self.activity = self.activity[:200]

    def persist_map(self):
        s = self.state_store.load()
        s["copy_map"] = self.copy_map
        self.state_store.save(s)

    def update_preferences(self, updates):
        clean = {key: updates[key] for key in COPY_PREFERENCE_DEFAULTS if key in updates}
        if "max_copied_trades_per_slave" in clean:
            clean["max_copied_trades_per_slave"] = max(1, min(100, int(clean["max_copied_trades_per_slave"] or 1)))
        if "risk_reward_ratio" in clean:
            clean["risk_reward_ratio"] = max(1.0, float(clean["risk_reward_ratio"] or 2.0))
        if "shoulder_strength" in clean:
            clean["shoulder_strength"] = max(1, min(5, int(clean["shoulder_strength"] or 2)))
        if "shoulder_buffer_points" in clean:
            clean["shoulder_buffer_points"] = max(0.0, float(clean["shoulder_buffer_points"] or 0.0))
        with self.lock:
            self.preferences.update(clean)
            if self.config is not None:
                self.config.update(clean)
            s = self.state_store.load()
            s["copy_preferences"] = dict(self.preferences)
            if s.get("copy_enabled") and isinstance(s.get("copy_config"), dict):
                s["copy_config"].update(clean)
            self.state_store.save(s)
        return dict(self.preferences)

    def stop(self):
        thread = self.thread
        if thread and thread.is_alive():
            self.stop_event.set()
            # Stop must return quickly for the web request, but never clear the
            # event while a slow MT5 call is still unwinding. The old thread
            # keeps its stop signal and exits as soon as that call returns.
            thread.join(timeout=0.25)
            if not thread.is_alive():
                self.thread = None
        else:
            self.thread = None
        self.status = "stopped"
        with self.lock:
            self.pending.clear()
            self.ignored.clear()

    def start(self, cfg):
        self.stop()
        if self.thread and self.thread.is_alive():
            raise RuntimeError("Copy Trader is still stopping the previous session. Try again in a few seconds.")
        self.thread = None
        self.stop_event = threading.Event()
        self.config = dict(cfg)
        self.update_preferences(cfg)
        saved = self.state_store.load()
        saved["copy_config"] = dict(self.config)
        saved["copy_preferences"] = dict(self.preferences)
        self.state_store.save(saved)
        try:
            existing = self.pool.call(cfg["master_account_id"], "positions")
            self.ignored = {str(int(p["ticket"])) for p in existing}
        except Exception:
            self.ignored = set()
        self.status = "running"
        self.thread = threading.Thread(target=self.run, daemon=True, name="KOOLKID-CopyEngine")
        self.thread.start()
        self.log("copy_started", master=cfg["master_account_id"], slaves=cfg["slave_account_ids"])

    def passes_filter(self, p):
        f = self.config["source_filter"]
        magic = int(p.get("magic") or 0)
        if f == "all": return True
        if f == "manual": return magic == 0
        if f == "ea": return magic != 0 and magic != COPY_MAGIC
        if f == "magic": return magic == int(self.config.get("magic_number") or 0)
        return True

    def side(self, p):
        if p.get("side"): return str(p["side"]).lower()
        return "buy" if int(p.get("type") or 0) == 0 else "sell"

    def shoulder_target(self, entry, sl, side):
        if not bool((self.config or {}).get("trail_by_shoulders")):
            return 0.0
        entry = float(entry or 0)
        sl = float(sl or 0)
        ratio = max(1.0, float((self.config or {}).get("risk_reward_ratio") or 2.0))
        if entry <= 0 or sl <= 0:
            raise RuntimeError("Trail by Shoulders requires a valid master stop loss.")
        risk = abs(entry - sl)
        if risk <= 0:
            raise RuntimeError("Trail by Shoulders requires a non-zero stop distance.")
        side = str(side or "").lower()
        if side == "buy":
            if sl >= entry:
                raise RuntimeError("Trail by Shoulders requires the BUY stop below entry.")
            return entry + risk * ratio
        if sl <= entry:
            raise RuntimeError("Trail by Shoulders requires the SELL stop above entry.")
        return entry - risk * ratio

    def _open_copy_positions(self, slave_id):
        try:
            rows = self.pool.call(slave_id, "positions", timeout=8)
        except Exception as exc:
            raise RuntimeError(f"Could not verify copy slots for {slave_id}: {exc}") from exc
        return [
            row for row in rows
            if int(row.get("magic") or 0) == COPY_MAGIC
            or str(row.get("comment") or "").startswith("KKCOPY:")
        ]

    def _copy_slot_available(self, slave_id):
        cfg = self.config or {}
        if not bool(cfg.get("limit_copied_trades")):
            return True, None
        limit = max(1, int(cfg.get("max_copied_trades_per_slave") or 1))
        count = len(self._open_copy_positions(slave_id))
        if count >= limit:
            return False, f"Copy limit reached ({count}/{limit}) for {slave_id}."
        return True, {"count": count, "limit": limit}

    @staticmethod
    def _swing_indexes(candles, field, strength, mode):
        indexes = []
        for index in range(strength, len(candles) - strength):
            value = float(candles[index][field])
            neighbors = [
                float(candles[i][field])
                for i in range(index - strength, index + strength + 1)
                if i != index
            ]
            if mode == "low" and all(value < item for item in neighbors):
                indexes.append(index)
            elif mode == "high" and all(value > item for item in neighbors):
                indexes.append(index)
        return indexes

    @classmethod
    def structure_shoulder_stop(
        cls, candles, side, point, current_sl=0.0, current_price=0.0,
        strength=2, buffer_points=5.0,
    ):
        # MT5 returns the current/forming candle last. Never use it for structure.
        closed = list(candles or [])[:-1]
        strength = max(1, int(strength or 2))
        if len(closed) < strength * 2 + 6:
            return None
        side = str(side or "").lower()
        point = max(float(point or 0.0), 1e-12)
        buffer = max(0.0, float(buffer_points or 0.0)) * point
        current_sl = float(current_sl or 0.0)
        current_price = float(current_price or closed[-1].get("close") or 0.0)

        if side == "buy":
            swings = cls._swing_indexes(closed, "low", strength, "low")
            for older, newer in zip(reversed(swings[:-1]), reversed(swings[1:])):
                older_low = float(closed[older]["low"])
                newer_low = float(closed[newer]["low"])
                if newer_low <= older_low:
                    continue
                structure_high = max(float(row["high"]) for row in closed[older:newer + 1])
                continuation = any(
                    float(row["close"]) > structure_high
                    for row in closed[newer + strength + 1:]
                )
                if not continuation:
                    continue
                candidate = newer_low - buffer
                if candidate >= current_price:
                    continue
                if current_sl > 0 and candidate <= current_sl + point * 0.25:
                    continue
                return {
                    "sl": candidate,
                    "shoulder_time": int(closed[newer].get("time") or 0),
                    "shoulder_price": newer_low,
                    "structure_break": structure_high,
                }
        else:
            swings = cls._swing_indexes(closed, "high", strength, "high")
            for older, newer in zip(reversed(swings[:-1]), reversed(swings[1:])):
                older_high = float(closed[older]["high"])
                newer_high = float(closed[newer]["high"])
                if newer_high >= older_high:
                    continue
                structure_low = min(float(row["low"]) for row in closed[older:newer + 1])
                continuation = any(
                    float(row["close"]) < structure_low
                    for row in closed[newer + strength + 1:]
                )
                if not continuation:
                    continue
                candidate = newer_high + buffer
                if current_price > 0 and candidate <= current_price:
                    continue
                if current_sl > 0 and candidate >= current_sl - point * 0.25:
                    continue
                return {
                    "sl": candidate,
                    "shoulder_time": int(closed[newer].get("time") or 0),
                    "shoulder_price": newer_high,
                    "structure_break": structure_low,
                }
        return None

    def _trail_copy_by_structure(self, slave_id, meta):
        ticket = int(meta.get("ticket") or 0)
        if not ticket:
            return False
        now = time.time()
        if now - float(meta.get("_structure_scan_at") or 0) < 5.0:
            return False
        meta["_structure_scan_at"] = now
        positions = self.pool.call(slave_id, "positions", timeout=8)
        position = next((row for row in positions if int(row.get("ticket") or 0) == ticket), None)
        if not position:
            return False

        symbol = str(position.get("symbol") or meta.get("symbol") or "")
        if not symbol:
            return False
        cfg = self.config or {}
        timeframe = str(cfg.get("shoulder_timeframe") or "M5").upper()
        candles = self.pool.call(
            slave_id, "candles",
            {"symbol": symbol, "timeframe": timeframe, "count": 120},
            timeout=12,
        )
        symbol_info = self.pool.call(slave_id, "symbol_info", {"symbol": symbol}, timeout=8) or {}
        point = float(symbol_info.get("point") or 0)
        side = self.side(position)
        current_sl = float(position.get("sl") or meta.get("last_sl") or 0)
        current_price = float(position.get("price_current") or position.get("current_price") or 0)
        shoulder = self.structure_shoulder_stop(
            candles,
            side,
            point,
            current_sl=current_sl,
            current_price=current_price,
            strength=int(cfg.get("shoulder_strength") or 2),
            buffer_points=float(cfg.get("shoulder_buffer_points") or 5.0),
        )
        if not shoulder:
            return False
        if int(shoulder["shoulder_time"]) <= int(meta.get("last_shoulder_time") or 0):
            return False

        new_sl = float(shoulder["sl"])
        tp = float(meta.get("last_tp") or position.get("tp") or 0)
        self.pool.call(
            slave_id,
            "modify_position",
            {"ticket": ticket, "sl": new_sl, "tp": tp},
            timeout=15,
        )
        meta["last_sl"] = new_sl
        meta["last_shoulder_time"] = int(shoulder["shoulder_time"])
        meta["last_shoulder_price"] = float(shoulder["shoulder_price"])
        meta["last_structure_break"] = float(shoulder["structure_break"])
        self.persist_map()
        self.log(
            "shoulder_trail",
            slave=slave_id,
            slave_ticket=ticket,
            symbol=symbol,
            side=side,
            sl=new_sl,
            shoulder_price=meta["last_shoulder_price"],
            timeframe=timeframe,
        )
        return True

    def _confirm_copy_closed(self, slave_id, ticket):
        positions = self.pool.call(slave_id, "positions", timeout=5)
        return not any(int(row.get("ticket") or 0) == int(ticket) for row in positions)

    def _close_mapped_slave(self, master_ticket, slave_id, meta):
        ticket = int(meta.get("ticket") or 0)
        if not ticket:
            return True
        try:
            self.pool.call(slave_id, "close_position", {"ticket": ticket}, timeout=12)
        except Exception as exc:
            # A broker timeout can happen after MT5 actually closed the trade.
            # Confirm the ticket before deciding whether this needs a retry.
            try:
                if self._confirm_copy_closed(slave_id, ticket):
                    self.log("copied_close_confirmed", master_ticket=master_ticket, slave=slave_id, slave_ticket=ticket)
                    return True
            except Exception as confirm_exc:
                meta["last_close_error"] = f"{exc}; confirmation failed: {confirm_exc}"
            else:
                meta["last_close_error"] = str(exc)
            meta["close_retry_count"] = int(meta.get("close_retry_count") or 0) + 1
            meta["last_close_attempt_at"] = time.time()
            self.persist_map()
            self.log(
                "copied_close_retry",
                master_ticket=master_ticket,
                slave=slave_id,
                slave_ticket=ticket,
                attempt=meta["close_retry_count"],
                error=meta.get("last_close_error"),
            )
            return False

        # Do not forget the mapping until MT5 confirms the ticket is gone.
        last_error = ""
        for _ in range(3):
            try:
                if self._confirm_copy_closed(slave_id, ticket):
                    self.log("copied_close", master_ticket=master_ticket, slave=slave_id, slave_ticket=ticket)
                    return True
                last_error = "MT5 still reports the copied ticket as open."
            except Exception as exc:
                last_error = str(exc)
            time.sleep(0.2)

        meta["close_retry_count"] = int(meta.get("close_retry_count") or 0) + 1
        meta["last_close_attempt_at"] = time.time()
        meta["last_close_error"] = last_error or "Copied close was not confirmed."
        self.persist_map()
        self.log(
            "copied_close_retry",
            master_ticket=master_ticket,
            slave=slave_id,
            slave_ticket=ticket,
            attempt=meta["close_retry_count"],
            error=meta["last_close_error"],
        )
        return False

    def _close_master_mappings(self, master_ticket, cfg):
        mapped = self.copy_map.get(master_ticket, {})
        close_targets = [
            (slave_id, meta)
            for slave_id, meta in list(mapped.items())
            if slave_id in cfg.get("slave_account_ids", [])
        ]
        if not close_targets:
            return not bool(mapped)

        def close_slave(target):
            slave_id, meta = target
            try:
                closed = self._close_mapped_slave(master_ticket, slave_id, meta)
                return slave_id, closed
            except Exception as exc:
                meta["close_retry_count"] = int(meta.get("close_retry_count") or 0) + 1
                meta["last_close_attempt_at"] = time.time()
                meta["last_close_error"] = str(exc)
                self.log(
                    "copied_close_retry",
                    master_ticket=master_ticket,
                    slave=slave_id,
                    slave_ticket=int(meta.get("ticket") or 0),
                    attempt=meta["close_retry_count"],
                    error=str(exc),
                )
                return slave_id, False

        with ThreadPoolExecutor(max_workers=len(close_targets) or 1) as executor:
            results = list(executor.map(close_slave, close_targets))

        changed = False
        for slave_id, closed in results:
            if closed and slave_id in mapped:
                mapped.pop(slave_id, None)
                changed = True
        if not mapped:
            self.copy_map.pop(master_ticket, None)
            changed = True
        if changed or any(not closed for _, closed in results):
            self.persist_map()
        return master_ticket not in self.copy_map

    def account_budget(self, account_id):
        cfg = (self.state_store.load().get("accounts") or {}).get(str(account_id)) or {}
        value = cfg.get("budget")
        try:
            return float(value) if value is not None and float(value) > 0 else None
        except (TypeError, ValueError):
            return None

    def effective_equity(self, account_id, account_info):
        equity = float((account_info or {}).get("equity") or 0)
        budget = self.account_budget(account_id)
        return min(equity, budget) if budget is not None and equity > 0 else (budget if budget is not None else equity)

    def budget_status(self, account_id):
        cfg = (self.state_store.load().get("accounts") or {}).get(str(account_id))
        if cfg is None:
            raise RuntimeError("MT5 account is not registered in this workspace.")
        budget = self.account_budget(account_id)
        info = self.pool.call(account_id, "account_info", timeout=5) if account_id in self.pool.ids() else {}
        balance = float(info.get("balance") or 0)
        equity = float(info.get("equity") or balance or 0)
        margin = float(info.get("margin") or 0)
        virtual_balance = min(balance, budget) if budget is not None and balance > 0 else (budget if budget is not None else balance)
        virtual_equity = min(equity, budget) if budget is not None and equity > 0 else (budget if budget is not None else equity)
        return {
            "budget_enabled": budget is not None, "budget": budget,
            "actual_balance": balance, "actual_equity": equity,
            "virtual_balance": virtual_balance, "virtual_equity": virtual_equity,
            "virtual_free_margin": max(0.0, virtual_equity - margin), "margin_used": margin,
        }

    def enforce_budget(self, account_id, order_payload):
        budget = self.account_budget(account_id)
        if budget is None:
            return None
        status = self.budget_status(account_id)
        required = self.pool.call(account_id, "margin_required", {
            "symbol": order_payload["symbol"], "side": order_payload.get("side") or "buy",
            "volume": float(order_payload.get("volume") or 0),
        }, timeout=8)
        needed = float(required.get("margin") or 0)
        available = float(status.get("virtual_free_margin") or 0)
        if needed > available + 1e-9:
            raise RuntimeError(
                f"Budget guard blocked this trade. Required margin {needed:.2f} exceeds virtual free margin {available:.2f} "
                f"from the {budget:.2f} account budget."
            )
        return {**status, "required_margin": needed}

    def target_volume(self, master_pos, master_info, slave_info, master_id=None, slave_id=None):
        m = float(master_pos.get("volume") or 0.01)
        mode = self.config["lot_mode"]
        if mode == "fixed":
            return float(self.config["fixed_lot"])
        if mode == "multiplier":
            return max(0.01, m * float(self.config["multiplier"]))
        if mode == "equity_proportional":
            me = self.effective_equity(master_id, master_info) if master_id else float(master_info.get("equity") or 0)
            se = self.effective_equity(slave_id, slave_info) if slave_id else float(slave_info.get("equity") or 0)
            return m if me <= 0 else max(0.01, m * (se / me))
        return m

    def _copy_to_slave(self, master_ticket, pos, master_info, slave_id):
        slot_ok, slot = self._copy_slot_available(slave_id)
        if not slot_ok:
            self.log("copy_limit_skipped", master_ticket=master_ticket, slave=slave_id, reason=slot)
            return {"ok": False, "skipped": True, "error": slot}
        slave_info = self.pool.call(slave_id, "account_info")
        rt = self.pool.items[slave_id]
        aliases = rt.config.get("symbol_aliases") or {}
        symbol = aliases.get(pos["symbol"], pos["symbol"])
        master_id = str((self.config or {}).get("master_account_id") or "")
        volume = self.target_volume(pos, master_info, slave_info, master_id=master_id, slave_id=slave_id)
        tag = f"KKCOPY:{master_ticket}"[:31]
        side = self.side(pos)
        stop_loss = float(pos.get("sl") or 0)
        master_entry = float(pos.get("price_open") or pos.get("open_price") or 0)
        shoulder_tp = self.shoulder_target(master_entry, stop_loss, side)
        payload = {
            "symbol": symbol,
            "side": side,
            "volume": volume,
            "sl": stop_loss,
            "tp": shoulder_tp if shoulder_tp else float(pos.get("tp") or 0),
            "magic": COPY_MAGIC,
            "comment": tag,
        }
        try:
            self.enforce_budget(slave_id, payload)
            result = self.pool.call(slave_id, "open_trade", payload, timeout=35)
        except TimeoutError:
            positions = self.pool.call(slave_id, "positions", timeout=15)
            match = next((row for row in positions if str(row.get("comment") or "").startswith(tag)), None)
            if not match:
                raise RuntimeError("MT5 did not confirm the copied order before the safety timeout.")
            result = {"retcode": 10009, "ticket": int(match.get("ticket") or 0), "reconciled_after_timeout": True}
        slave_ticket = int(result.get("ticket") or 0)
        if not slave_ticket:
            raise RuntimeError(f"Could not resolve slave ticket: {result}")

        final_tp = float(payload.get("tp") or 0)
        slave_pos = None
        if bool((self.config or {}).get("trail_by_shoulders")):
            slave_positions = self.pool.call(slave_id, "positions", timeout=10)
            slave_pos = next((row for row in slave_positions if int(row.get("ticket") or 0) == slave_ticket), None)
            fill_price = float((slave_pos or {}).get("price_open") or (slave_pos or {}).get("open_price") or result.get("price") or master_entry)
            final_tp = self.shoulder_target(fill_price, stop_loss, side)
            self.pool.call(
                slave_id,
                "modify_position",
                {"ticket": slave_ticket, "sl": stop_loss, "tp": final_tp},
                timeout=15,
            )

        self.copy_map.setdefault(master_ticket, {})[slave_id] = {
            "ticket": slave_ticket,
            "symbol": symbol,
            "side": side,
            "entry": float((slave_pos or {}).get("price_open") or (slave_pos or {}).get("open_price") or result.get("price") or master_entry),
            "initial_sl": stop_loss,
            "last_sl": stop_loss,
            "last_tp": final_tp,
            "trail_by_shoulders": bool((self.config or {}).get("trail_by_shoulders")),
        }
        self.persist_map()
        self.log(
            "copied_open",
            master_ticket=master_ticket,
            slave=slave_id,
            slave_ticket=slave_ticket,
            trail_by_shoulders=bool((self.config or {}).get("trail_by_shoulders")),
            target_tp=final_tp,
        )
        return {"ok": True, "ticket": slave_ticket}

    def pending_items(self):
        with self.lock:
            return [dict(item) for item in self.pending.values()]

    def register_concurrent_open(self, master_ticket, position, slave_results):
        ticket = str(int(master_ticket))
        with self.lock:
            self.ignored.add(ticket)
            self.pending.pop(ticket, None)
            mapped = {}
            for slave_id, row in slave_results.items():
                result = row.get("result") or {}
                slave_ticket = int(result.get("ticket") or result.get("order") or 0)
                if row.get("ok") and slave_ticket:
                    mapped[slave_id] = {"ticket": slave_ticket, "last_sl": float(position.get("sl") or 0), "last_tp": float(position.get("tp") or 0)}
            if mapped:
                self.copy_map[ticket] = mapped
                self.persist_map()
        self.log("concurrent_open_registered", master_ticket=ticket, slaves=list(mapped))

    def decide(self, master_ticket, should_copy, slave_ids):
        ticket = str(int(master_ticket))
        with self.lock:
            item = self.pending.get(ticket)
            if not item:
                raise RuntimeError("This copy request is no longer pending.")
            configured = list(self.config.get("slave_account_ids") or [])
            selected = list(dict.fromkeys(slave_ids or configured)) if should_copy else []
            invalid = [aid for aid in selected if aid not in configured]
            if invalid:
                raise RuntimeError("Invalid slave selection: " + ", ".join(invalid))
            self.pending.pop(ticket, None)
            self.ignored.add(ticket)

        if not should_copy:
            self.log("copy_skipped", master_ticket=ticket)
            return {"ok": True, "decision": "master_only", "results": {}}

        results = {}
        master_info = self.pool.call(self.config["master_account_id"], "account_info")
        started = time.time()
        def submit(slave_id):
            began = time.time()
            try:
                result = self._copy_to_slave(ticket, item["position"], master_info, slave_id)
                return slave_id, {**result, "elapsed_ms": round((time.time() - began) * 1000, 1)}
            except Exception as exc:
                self.log("copy_error", master_ticket=ticket, slave=slave_id, error=str(exc))
                return slave_id, {"ok": False, "error": str(exc), "elapsed_ms": round((time.time() - began) * 1000, 1)}
        with ThreadPoolExecutor(max_workers=len(selected) or 1) as executor:
            for future in as_completed([executor.submit(submit, slave_id) for slave_id in selected]):
                slave_id, result = future.result()
                results[slave_id] = result
        filled = [row["elapsed_ms"] for row in results.values() if row.get("ok")]
        elapsed_ms = round((time.time() - started) * 1000, 1)
        fill_spread_ms = round(max(filled) - min(filled), 1) if len(filled) > 1 else 0.0
        self.log(
            "copy_completed",
            master_ticket=ticket,
            elapsed_ms=elapsed_ms,
            fill_spread_ms=fill_spread_ms,
            slave_count=len(selected),
            filled_count=sum(1 for row in results.values() if row.get("ok")),
            results=results,
        )
        return {"ok": True, "decision": "copied", "results": results,
                "elapsed_ms": elapsed_ms, "fill_spread_ms": fill_spread_ms}

    def run(self):
        cfg = self.config
        try:
            while not self.stop_event.is_set():
                try:
                    if time.time() < self.pause_until:
                        time.sleep(0.1)
                        continue
                    master_positions = self.pool.call(cfg["master_account_id"], "positions")
                    if self.stop_event.is_set():
                        return
                    master_info = self.pool.call(cfg["master_account_id"], "account_info")
                    if self.stop_event.is_set():
                        return
                    current = {str(int(p["ticket"])): p for p in master_positions if self.passes_filter(p)}

                    # New master positions can either wait for approval (normal Copy Trading)
                    # or copy immediately when the AI-page "Copy Trades From Anywhere" toggle
                    # has restarted the link with approval_required=False.
                    for master_ticket, pos in current.items():
                        if self.stop_event.is_set():
                            return
                        if master_ticket in self.copy_map or master_ticket in self.ignored:
                            continue
                        with self.lock:
                            if master_ticket in self.pending:
                                continue
                            self.pending[master_ticket] = {
                                "master_ticket": int(master_ticket),
                                "master_account_id": cfg["master_account_id"],
                                "slave_account_ids": list(cfg["slave_account_ids"]),
                                "position": dict(pos),
                                "created_at": time.time(),
                            }
                        if bool(cfg.get("approval_required", True)):
                            self.log("approval_pending", master_ticket=master_ticket, symbol=pos.get("symbol"))
                        else:
                            self.log("auto_copy_detected", master_ticket=master_ticket, symbol=pos.get("symbol"))
                            try:
                                self.decide(int(master_ticket), True, list(cfg.get("slave_account_ids") or []))
                            except Exception as exc:
                                with self.lock:
                                    self.pending.pop(master_ticket, None)
                                    self.ignored.add(master_ticket)
                                self.log("copy_error", master_ticket=master_ticket, error=str(exc))

                    # Normal copies mirror the master's protection. Shoulder mode
                    # is independent: it reads completed slave-market candles and only
                    # advances the slave stop behind confirmed HL/LH structure.
                    for master_ticket, pos in current.items():
                        for slave_id, meta in self.copy_map.get(master_ticket, {}).items():
                            if slave_id not in cfg["slave_account_ids"]:
                                continue
                            shoulder_mode = bool(cfg.get("trail_by_shoulders"))
                            if shoulder_mode:
                                try:
                                    self._trail_copy_by_structure(slave_id, meta)
                                except Exception as exc:
                                    self.log("copy_error", master_ticket=master_ticket, slave=slave_id, error=str(exc))
                                continue

                            sl = float(pos.get("sl") or 0)
                            tp = float(pos.get("tp") or 0)
                            sl_changed = sl != float(meta.get("last_sl") or 0)
                            tp_changed = tp != float(meta.get("last_tp") or 0)
                            if sl_changed or tp_changed:
                                try:
                                    self.pool.call(
                                        slave_id,
                                        "modify_position",
                                        {"ticket": int(meta["ticket"]), "sl": sl, "tp": tp},
                                    )
                                    meta["last_sl"], meta["last_tp"] = sl, tp
                                    self.persist_map()
                                    self.log("copied_modify", master_ticket=master_ticket, slave=slave_id, trail_by_shoulders=False)
                                except Exception as exc:
                                    self.log("copy_error", master_ticket=master_ticket, slave=slave_id, error=str(exc))

                    # Close slave copies when the master ticket disappears.
                    # This is identical in approval mode and Copy Trades From
                    # Anywhere; failed closes stay mapped and retry next cycle.
                    for master_ticket in list(self.copy_map):
                        if master_ticket in current:
                            continue
                        self._close_master_mappings(master_ticket, cfg)

                    with self.lock:
                        for master_ticket in list(self.pending):
                            if master_ticket not in current:
                                self.pending.pop(master_ticket, None)
                                self.ignored.add(master_ticket)
                                self.log("approval_expired", master_ticket=master_ticket)

                    time.sleep(max(1.0, int(cfg["poll_ms"]) / 1000))
                except Exception as exc:
                    self.log("engine_error", error=str(exc))
                    time.sleep(0.5)
        finally:
            self.status = "stopped"

    def snapshot(self):
        return {
            "status": self.status,
            "config": self.config,
            "preferences": dict(self.preferences),
            "copy_map": self.copy_map,
            "activity": self.activity[:100],
            "pending_count": len(self.pending),
        }
