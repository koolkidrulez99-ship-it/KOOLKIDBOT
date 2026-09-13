from __future__ import annotations
import threading, time

COPY_MAGIC = 987654

class CopyEngine:
    def __init__(self, pool, state):
        self.pool = pool
        self.state_store = state
        self.thread = None
        self.stop_event = threading.Event()
        self.config = None
        self.status = "stopped"
        self.activity = []
        self.copy_map = self.state_store.load().get("copy_map", {})
        self.pending = {}
        self.ignored = set()
        self.lock = threading.RLock()

    def log(self, event, **extra):
        self.activity.insert(0, {"time": time.time(), "event": event, **extra})
        self.activity = self.activity[:200]

    def persist_map(self):
        s = self.state_store.load()
        s["copy_map"] = self.copy_map
        self.state_store.save(s)

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.thread.join(timeout=3)
        self.thread = None
        self.stop_event.clear()
        self.status = "stopped"
        with self.lock:
            self.pending.clear()
            self.ignored.clear()

    def start(self, cfg):
        self.stop()
        self.config = cfg
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

    def target_volume(self, master_pos, master_info, slave_info):
        m = float(master_pos.get("volume") or 0.01)
        mode = self.config["lot_mode"]
        if mode == "fixed":
            return float(self.config["fixed_lot"])
        if mode == "multiplier":
            return max(0.01, m * float(self.config["multiplier"]))
        if mode == "equity_proportional":
            me = float(master_info.get("equity") or 0)
            se = float(slave_info.get("equity") or 0)
            return m if me <= 0 else max(0.01, m * (se / me))
        return m

    def _copy_to_slave(self, master_ticket, pos, master_info, slave_id):
        slave_info = self.pool.call(slave_id, "account_info")
        rt = self.pool.items[slave_id]
        aliases = rt.config.get("symbol_aliases") or {}
        symbol = aliases.get(pos["symbol"], pos["symbol"])
        volume = self.target_volume(pos, master_info, slave_info)
        tag = f"KKCOPY:{master_ticket}"[:31]
        payload = {
            "symbol": symbol,
            "side": self.side(pos),
            "volume": volume,
            "sl": float(pos.get("sl") or 0),
            "tp": float(pos.get("tp") or 0),
            "magic": COPY_MAGIC,
            "comment": tag,
        }
        try:
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
        self.copy_map.setdefault(master_ticket, {})[slave_id] = {
            "ticket": slave_ticket,
            "last_sl": float(pos.get("sl") or 0),
            "last_tp": float(pos.get("tp") or 0),
        }
        self.persist_map()
        self.log("copied_open", master_ticket=master_ticket, slave=slave_id, slave_ticket=slave_ticket)
        return {"ok": True, "ticket": slave_ticket}

    def pending_items(self):
        with self.lock:
            return [dict(item) for item in self.pending.values()]

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
        for slave_id in selected:
            try:
                results[slave_id] = self._copy_to_slave(ticket, item["position"], master_info, slave_id)
            except Exception as exc:
                results[slave_id] = {"ok": False, "error": str(exc)}
                self.log("copy_error", master_ticket=ticket, slave=slave_id, error=str(exc))
        return {"ok": True, "decision": "copied", "results": results}

    def run(self):
        cfg = self.config
        try:
            while not self.stop_event.is_set():
                try:
                    master_positions = self.pool.call(cfg["master_account_id"], "positions")
                    master_info = self.pool.call(cfg["master_account_id"], "account_info")
                    current = {str(int(p["ticket"])): p for p in master_positions if self.passes_filter(p)}

                    # Queue new master positions for explicit user approval.
                    for master_ticket, pos in current.items():
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
                        self.log("approval_pending", master_ticket=master_ticket, symbol=pos.get("symbol"))

                    # Sync SL/TP.
                    for master_ticket, pos in current.items():
                        for slave_id, meta in self.copy_map.get(master_ticket, {}).items():
                            if slave_id not in cfg["slave_account_ids"]:
                                continue
                            sl = float(pos.get("sl") or 0)
                            tp = float(pos.get("tp") or 0)
                            if sl != float(meta.get("last_sl") or 0) or tp != float(meta.get("last_tp") or 0):
                                try:
                                    self.pool.call(slave_id, "modify_position", {"ticket": int(meta["ticket"]), "sl": sl, "tp": tp})
                                    meta["last_sl"], meta["last_tp"] = sl, tp
                                    self.persist_map()
                                    self.log("copied_modify", master_ticket=master_ticket, slave=slave_id)
                                except Exception as exc:
                                    self.log("copy_error", master_ticket=master_ticket, slave=slave_id, error=str(exc))

                    # Close slave copies when master closes.
                    for master_ticket in list(self.copy_map):
                        if master_ticket in current:
                            continue
                        for slave_id, meta in list(self.copy_map.get(master_ticket, {}).items()):
                            if slave_id not in cfg["slave_account_ids"]:
                                continue
                            try:
                                ticket = int(meta["ticket"])
                                try:
                                    self.pool.call(slave_id, "close_position", {"ticket": ticket}, timeout=35)
                                except TimeoutError:
                                    positions = self.pool.call(slave_id, "positions", timeout=15)
                                    if any(int(row.get("ticket") or 0) == ticket for row in positions):
                                        raise RuntimeError("MT5 did not confirm the copied close before the safety timeout.")
                                self.log("copied_close", master_ticket=master_ticket, slave=slave_id)
                            except Exception as exc:
                                self.log("copy_error", master_ticket=master_ticket, slave=slave_id, error=str(exc))
                        self.copy_map.pop(master_ticket, None)
                        self.persist_map()

                    with self.lock:
                        for master_ticket in list(self.pending):
                            if master_ticket not in current:
                                self.pending.pop(master_ticket, None)
                                self.ignored.add(master_ticket)
                                self.log("approval_expired", master_ticket=master_ticket)

                    time.sleep(max(0.2, int(cfg["poll_ms"]) / 1000))
                except Exception as exc:
                    self.log("engine_error", error=str(exc))
                    time.sleep(0.5)
        finally:
            self.status = "stopped"

    def snapshot(self):
        return {
            "status": self.status,
            "config": self.config,
            "copy_map": self.copy_map,
            "activity": self.activity[:100],
            "pending_count": len(self.pending),
        }
