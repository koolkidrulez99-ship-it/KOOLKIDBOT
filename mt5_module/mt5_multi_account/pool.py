from __future__ import annotations
import ctypes, multiprocessing as mp, os, threading, time, uuid
from ctypes import wintypes
from pathlib import Path
from dataclasses import dataclass
from .worker import run_worker
from .models import MAX_ACCOUNTS

@dataclass
class Runtime:
    config: dict
    process: object
    qin: object
    qout: object
    lock: threading.RLock
    cache: dict
    password: str = ""

    def call(self, op, payload=None, timeout=15):
        deadline = time.monotonic() + timeout
        if not self.lock.acquire(timeout=max(0.01, timeout)):
            raise TimeoutError(f"Worker busy timeout: {op}")
        try:
            rid = uuid.uuid4().hex
            self.qin.put({"id": rid, "op": op, "payload": payload or {}})
            while time.monotonic() < deadline:
                if not self.process.is_alive():
                    raise RuntimeError("Account worker stopped")
                try:
                    remaining = max(0.01, deadline - time.monotonic())
                    msg = self.qout.get(timeout=min(0.25, remaining))
                except Exception:
                    continue
                if msg.get("id") != rid:
                    continue
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error") or "Worker request failed")
                return msg.get("result")
            raise TimeoutError(f"Worker timeout: {op}")
        finally:
            self.lock.release()

class Pool:
    def __init__(self):
        self.ctx = mp.get_context("spawn")
        self.items = {}
        self.lock = threading.RLock()
        self.connect_lock = threading.Lock()
        self.pending = {}
        self.failures = {}
        self.recovery = {}
        self.stopping = False
        self.monitor = threading.Thread(target=self._monitor, daemon=True, name="KOOLKID-MT5-Session-Monitor")
        self.monitor.start()

    def _monitor(self):
        while not self.stopping:
            now = time.time()
            with self.lock:
                candidates = [(aid, dict(rt.config), rt.password) for aid, rt in self.items.items()
                              if not rt.process.is_alive() and now >= self.recovery.get(aid, {}).get("next_at", 0)]
            for aid, cfg, password in candidates:
                self._recover(aid, cfg, password)
            time.sleep(1.0)

    def _recover(self, aid, cfg, password=""):
        state = self.recovery.setdefault(aid, {"attempt": 0, "next_at": 0, "error": ""})
        state["attempt"] += 1
        try:
            self.disconnect(aid, preserve_recovery=True)
            self.connect(cfg, password)
            self.failures[aid] = 0
            self.recovery.pop(aid, None)
        except Exception as exc:
            delay = min(60, 2 ** min(state["attempt"], 6))
            state.update({"next_at": time.time() + delay, "error": str(exc)})

    def record_failure(self, aid, error):
        count = self.failures.get(aid, 0) + 1
        self.failures[aid] = count
        # Timeouts can mean the terminal is busy executing an order. Recovery is
        # reserved for a worker process that has actually exited.

    def record_success(self, aid):
        self.failures[aid] = 0

    def connect(self, cfg, password=""):
        aid = cfg["account_id"]
        with self.connect_lock:
            with self.lock:
                if aid in self.items:
                    return self.status(aid)
                workspace_id = str(cfg.get("_workspace") or "")
                if sum(1 for runtime in self.items.values() if str(runtime.config.get("_workspace") or "") == workspace_id) >= MAX_ACCOUNTS:
                    raise RuntimeError("Maximum of 10 active accounts reached")
                terminal = str(Path(cfg.get("terminal_path") or "").resolve()) if cfg.get("terminal_path") else ""
                for existing_id, runtime in self.items.items():
                    if str(runtime.config.get("_workspace") or "") == workspace_id and int(runtime.config.get("login") or 0) == int(cfg.get("login") or 0):
                        raise RuntimeError(f"MT5 login #{cfg.get('login')} is already owned by {existing_id}.")
                    existing_terminal = str(Path(runtime.config.get("terminal_path") or "").resolve()) if runtime.config.get("terminal_path") else ""
                    if terminal and terminal == existing_terminal:
                        raise RuntimeError(f"MT5 terminal is already owned by {existing_id}.")
                cancel = threading.Event()
                self.pending[aid] = cancel
                # A forced service stop can leave this account's portable terminal
                # behind even though its worker is gone. Clear only that isolated
                # terminal before starting a replacement so MT5 IPC cannot attach
                # to a stale process. Exception: during one-time broker bootstrap,
                # the user completes the broker login in that exact private terminal
                # and the retry must attach to the still-running process.
                terminal_path = str(cfg.get("terminal_path") or "")
                bootstrap_marker = Path(terminal_path).parent / ".koolkid-broker-bootstrap-required" if terminal_path else None
                if not (bootstrap_marker and bootstrap_marker.is_file()):
                    self._stop_terminal(terminal_path)
                qin, qout = self.ctx.Queue(), self.ctx.Queue()
                proc = self.ctx.Process(target=run_worker, args=(cfg,password,qin,qout), daemon=True)
                proc.start()
            try:
                deadline = time.time()+75
                startup = None
                while time.time()<deadline:
                    if cancel.is_set():
                        raise RuntimeError("MT5 connection cancelled.")
                    try:
                        startup=qout.get(timeout=.25)
                        if startup.get("id")=="__startup__": break
                    except Exception:
                        if not proc.is_alive(): break
                if not startup or not startup.get("ok"):
                    if startup and startup.get("error"):
                        raise RuntimeError(startup["error"])
                    if proc.is_alive():
                        raise RuntimeError("MT5 account worker startup timed out before broker authentication finished.")
                    raise RuntimeError(f"MT5 account worker exited during startup (exit code {proc.exitcode}).")
                with self.lock:
                    self.items[aid] = Runtime(cfg, proc, qin, qout, threading.RLock(), {}, password)
                return self.status(aid)
            except Exception as exc:
                try: proc.terminate()
                except Exception: pass
                if "mt5 broker setup required" not in str(exc).lower():
                    self._stop_terminal(cfg.get("terminal_path"))
                raise
            finally:
                with self.lock:
                    self.pending.pop(aid, None)

    def cancel_connect(self, aid):
        with self.lock:
            cancel = self.pending.get(aid)
            if not cancel:
                return False
            cancel.set()
            return True

    @staticmethod
    def _stop_terminal(terminal_path):
        if not terminal_path:
            return
        target = Path(terminal_path).resolve()
        try:
            import psutil
            matches = []
            for process in psutil.process_iter(["exe"]):
                try:
                    if process.info.get("exe") and Path(process.info["exe"]).resolve() == target:
                        process.terminate()
                        matches.append(process)
                except (psutil.Error, OSError):
                    pass
            psutil.wait_procs(matches, timeout=5)
            return
        except ImportError:
            pass
        except Exception:
            return
        if os.name != "nt":
            return
        # Keep worker cleanup self-contained; the bridge venv intentionally
        # does not require psutil.
        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            return

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
            ]

        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        kernel = ctypes.windll.kernel32
        try:
            found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while found:
                if entry.szExeFile.lower() == target.name.lower():
                    handle = kernel.OpenProcess(0x0001 | 0x1000, False, entry.th32ProcessID)
                    if handle:
                        try:
                            size = wintypes.DWORD(32768)
                            buffer = ctypes.create_unicode_buffer(size.value)
                            if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                                if Path(buffer.value).resolve() == target:
                                    kernel.TerminateProcess(handle, 0)
                        finally:
                            kernel.CloseHandle(handle)
                found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)

    def disconnect(self, aid, preserve_recovery=False):
        rt = self.items.get(aid)
        if not rt: return
        try: rt.call("shutdown", timeout=3)
        except Exception: pass
        try:
            rt.process.join(timeout=2)
            if rt.process.is_alive(): rt.process.terminate()
        finally:
            self._stop_terminal(rt.config.get("terminal_path"))
            self.items.pop(aid, None)
            self.failures.pop(aid, None)
            if not preserve_recovery:
                self.recovery.pop(aid, None)

    def call(self, aid, op, payload=None, timeout=15):
        if aid not in self.items:
            raise RuntimeError(f"Account not connected: {aid}")
        try:
            result = self.items[aid].call(op,payload,timeout)
            if op in {"account_info", "positions", "quotes", "symbols"}:
                self.items[aid].cache[op] = result
            self.record_success(aid)
            return result
        except Exception as exc:
            self.record_failure(aid, exc)
            raise

    def cached(self, aid, op, default=None):
        rt = self.items.get(aid)
        return rt.cache.get(op, default) if rt else default

    def ids(self):
        with self.lock:
            items = list(self.items.items())
        return [aid for aid, rt in items if rt.process.is_alive()]

    def status(self, aid):
        rt=self.items.get(aid)
        if not rt:
            recovering = aid in self.recovery
            return {"account_id":aid,"connected":False,"connecting":aid in self.pending or recovering,"recovering":recovering,"error":self.recovery.get(aid, {}).get("error")}
        alive = rt.process.is_alive()
        recovering = aid in self.recovery
        return {"account_id":aid,"connected":alive and not recovering,"connecting":recovering,"recovering":recovering,"pid":rt.process.pid,**rt.config}

    def close_all(self):
        self.stopping = True
        for aid in list(self.items): self.disconnect(aid)
