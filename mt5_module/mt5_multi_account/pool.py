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

    def call(self, op, payload=None, timeout=15):
        with self.lock:
            rid = uuid.uuid4().hex
            self.qin.put({"id": rid, "op": op, "payload": payload or {}})
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not self.process.is_alive():
                    raise RuntimeError("Account worker stopped")
                try:
                    msg = self.qout.get(timeout=0.25)
                except Exception:
                    continue
                if msg.get("id") != rid:
                    continue
                if not msg.get("ok"):
                    raise RuntimeError(msg.get("error") or "Worker request failed")
                return msg.get("result")
            raise TimeoutError(f"Worker timeout: {op}")

class Pool:
    def __init__(self):
        self.ctx = mp.get_context("spawn")
        self.items = {}
        self.lock = threading.RLock()
        self.connect_lock = threading.Lock()
        self.pending = {}

    def connect(self, cfg, password=""):
        aid = cfg["account_id"]
        with self.connect_lock:
            with self.lock:
                if aid in self.items:
                    return self.status(aid)
                if len(self.items) >= MAX_ACCOUNTS:
                    raise RuntimeError("Maximum of 10 active accounts reached")
                terminal = str(Path(cfg.get("terminal_path") or "").resolve()) if cfg.get("terminal_path") else ""
                for existing_id, runtime in self.items.items():
                    if int(runtime.config.get("login") or 0) == int(cfg.get("login") or 0):
                        raise RuntimeError(f"MT5 login #{cfg.get('login')} is already owned by {existing_id}.")
                    existing_terminal = str(Path(runtime.config.get("terminal_path") or "").resolve()) if runtime.config.get("terminal_path") else ""
                    if terminal and terminal == existing_terminal:
                        raise RuntimeError(f"MT5 terminal is already owned by {existing_id}.")
                cancel = threading.Event()
                self.pending[aid] = cancel
                # A forced service stop can leave this account's portable terminal
                # behind even though its worker is gone. Clear only that isolated
                # terminal before starting a replacement so MT5 IPC cannot attach
                # to a stale process.
                self._stop_terminal(cfg.get("terminal_path"))
                qin, qout = self.ctx.Queue(), self.ctx.Queue()
                proc = self.ctx.Process(target=run_worker, args=(cfg,password,qin,qout), daemon=True)
                proc.start()
            try:
                deadline = time.time()+35
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
                    raise RuntimeError((startup or {}).get("error") or "Account worker failed to start")
                with self.lock:
                    self.items[aid] = Runtime(cfg,proc,qin,qout,threading.RLock())
                return self.status(aid)
            except Exception:
                try: proc.terminate()
                except Exception: pass
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

    def disconnect(self, aid):
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

    def call(self, aid, op, payload=None, timeout=15):
        if aid not in self.items:
            raise RuntimeError(f"Account not connected: {aid}")
        return self.items[aid].call(op,payload,timeout)

    def ids(self):
        return [aid for aid,rt in self.items.items() if rt.process.is_alive()]

    def status(self, aid):
        rt=self.items.get(aid)
        if not rt:
            return {"account_id":aid,"connected":False,"connecting":aid in self.pending}
        return {"account_id":aid,"connected":rt.process.is_alive(),"pid":rt.process.pid,**rt.config}

    def close_all(self):
        for aid in list(self.items): self.disconnect(aid)
