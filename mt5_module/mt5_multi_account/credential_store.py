from __future__ import annotations

import ctypes
import os
import re
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    in_blob, _buffer = _blob(data)
    out_blob = _DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "KOOLKID MT5 account credential",
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is only available on Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    in_blob, _buffer = _blob(data)
    out_blob = _DataBlob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


class CredentialStore:
    """Small Windows-only encrypted credential store.

    Passwords are never written into state.json. On Windows they are encrypted
    with DPAPI, which binds decryption to the Windows user profile that saved
    them. This is intended for reconnecting the user's own MT5 workers after a
    service restart or machine reboot.
    """

    def __init__(
        self,
        root: Path,
        *,
        protect: Callable[[bytes], bytes] | None = None,
        unprotect: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.root = Path(root)
        self._protect = protect or (_dpapi_protect if os.name == "nt" else None)
        self._unprotect = unprotect or (_dpapi_unprotect if os.name == "nt" else None)
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return self._protect is not None and self._unprotect is not None

    @staticmethod
    def _safe_name(account_id: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(account_id)).strip("._")
        return value or "account"

    def _path(self, account_id: str) -> Path:
        return self.root / f"{self._safe_name(account_id)}.bin"

    def save(self, account_id: str, password: str) -> bool:
        if not password or not self.available:
            return False
        raw = password.encode("utf-8")
        encrypted = self._protect(raw)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            target = self._path(account_id)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(encrypted)
            tmp.replace(target)
        return True

    def load(self, account_id: str) -> str:
        if not self.available:
            return ""
        target = self._path(account_id)
        with self._lock:
            if not target.is_file():
                return ""
            encrypted = target.read_bytes()
        try:
            return self._unprotect(encrypted).decode("utf-8")
        except Exception:
            return ""

    def delete(self, account_id: str) -> None:
        with self._lock:
            try:
                self._path(account_id).unlink(missing_ok=True)
            except OSError:
                pass

    def has(self, account_id: str) -> bool:
        return self._path(account_id).is_file()
