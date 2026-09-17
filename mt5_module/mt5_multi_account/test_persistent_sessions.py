from pathlib import Path

from .credential_store import CredentialStore
from .models import ConnectRequest


def test_credential_store_round_trip_without_plaintext(tmp_path: Path):
    def protect(raw: bytes) -> bytes:
        return bytes((value ^ 0x5A) for value in raw[::-1])

    def unprotect(raw: bytes) -> bytes:
        return bytes((value ^ 0x5A) for value in raw)[::-1]

    store = CredentialStore(tmp_path / "credentials", protect=protect, unprotect=unprotect)
    password = "demo-secret-123"
    assert store.save("session-1001", password)
    blob = (tmp_path / "credentials" / "session-1001.bin").read_bytes()
    assert password.encode() not in blob
    assert store.load("session-1001") == password
    assert store.has("session-1001") is True
    store.delete("session-1001")
    assert store.has("session-1001") is False


def test_connect_request_remembers_session_by_default():
    req = ConnectRequest(account_id="session-1001", login=1001, password="x")
    assert req.remember_session is True


def test_pool_recovery_reuses_runtime_password(monkeypatch):
    import sys
    import types

    worker_stub = types.ModuleType("mt5_module.mt5_multi_account.worker")
    worker_stub.run_worker = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "mt5_module.mt5_multi_account.worker", worker_stub)
    from .pool import Pool

    pool = Pool.__new__(Pool)
    pool.recovery = {}
    pool.failures = {}
    calls = []

    monkeypatch.setattr(pool, "disconnect", lambda aid, preserve_recovery=False: calls.append(("disconnect", aid, preserve_recovery)))
    monkeypatch.setattr(pool, "connect", lambda cfg, password="": calls.append(("connect", cfg["account_id"], password)))

    pool._recover("session-1001", {"account_id": "session-1001"}, "secret")
    assert ("connect", "session-1001", "secret") in calls
