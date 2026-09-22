import threading
import time

from mt5_module.mt5_multi_account import app as app_module


class FakeState:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def load(self):
        return dict(self.payload)


class FakePool:
    def __init__(self, ids):
        self._ids = list(ids)
        self.disconnected = []

    def ids(self):
        return list(self._ids)

    def disconnect(self, aid):
        self.disconnected.append(aid)
        if aid in self._ids:
            self._ids.remove(aid)


class FakeEngine:
    def __init__(self, status="stopped"):
        self.status = status


class FakeRuntime:
    def __init__(self, *, copy1=False, copy2=False, status="stopped", ids=None):
        self.started = True
        self.state = FakeState({"copy_enabled": copy1, "copy_enabled_2": copy2})
        self.copy_groups = {"1": FakeEngine(status), "2": FakeEngine("stopped")}
        self.last_activity = time.time() - 9999
        self.session_stop = threading.Event()
        self.pool = FakePool(ids or ["session-a", "session-b"])
        self.session_backoff = {"session-a": {"attempt": 1}}


def test_idle_non_copy_workspace_releases_terminals(monkeypatch):
    runtime = FakeRuntime()
    monkeypatch.setattr(app_module, "WORKSPACE_IDLE_SECONDS", 60)

    assert app_module._release_idle_workspace(runtime) is True
    assert runtime.pool.disconnected == ["session-a", "session-b"]
    assert runtime.started is False
    assert runtime.session_stop.is_set()
    assert runtime.session_backoff == {}


def test_copy_workspace_is_never_reaped(monkeypatch):
    runtime = FakeRuntime(copy1=True)
    monkeypatch.setattr(app_module, "WORKSPACE_IDLE_SECONDS", 60)

    assert app_module._release_idle_workspace(runtime) is False
    assert runtime.pool.disconnected == []
    assert runtime.started is True


def test_recent_workspace_is_not_reaped(monkeypatch):
    runtime = FakeRuntime()
    runtime.last_activity = time.time()
    monkeypatch.setattr(app_module, "WORKSPACE_IDLE_SECONDS", 60)

    assert app_module._release_idle_workspace(runtime) is False
    assert runtime.pool.disconnected == []


def test_copy_accounts_are_restored_before_unrelated_accounts(monkeypatch):
    state = FakeState({
        "copy_enabled": True,
        "copy_config": {
            "master_account_id": "master",
            "slave_account_ids": ["slave"],
        },
        "accounts": {
            "other": {"account_id": "other", "mode": "real"},
            "slave": {"account_id": "slave", "mode": "real"},
            "master": {"account_id": "master", "mode": "real"},
        },
    })
    monkeypatch.setattr(app_module, "STATE", state)

    rows = app_module._saved_real_accounts()

    assert [row["account_id"] for row in rows] == ["master", "slave", "other"]


def test_snapshot_cache_respects_ttl(monkeypatch):
    class CacheRuntime:
        read_cache = {}
        read_cache_lock = threading.RLock()

    runtime = CacheRuntime()
    clock = iter([100.0, 100.2, 101.5])
    monkeypatch.setattr(app_module.time, "monotonic", lambda: next(clock))

    app_module._snapshot_cache_set(runtime, "accounts", {"ok": True})
    assert app_module._snapshot_cache_get(runtime, "accounts", 1.0) == {"ok": True}
    assert app_module._snapshot_cache_get(runtime, "accounts", 1.0) is None


def test_saved_copy_workspace_filter(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "BASE", tmp_path)

    state_dir = tmp_path / "data" / "workspaces" / "copy-ws"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text('{"copy_enabled": true}', encoding="utf-8")

    idle_dir = tmp_path / "data" / "workspaces" / "idle-ws"
    idle_dir.mkdir(parents=True)
    (idle_dir / "state.json").write_text('{"accounts": {"session-a": {}}}', encoding="utf-8")

    assert app_module._workspace_saved_copy_enabled("copy-ws") is True
    assert app_module._workspace_saved_copy_enabled("idle-ws") is False


def test_remove_account_clears_position_and_history_snapshots(monkeypatch):
    class Runtime:
        session_backoff = {"session-a": {"attempt": 1}}
        read_cache = {
            "positions": {"positions": [{"account_id": "session-a"}]},
            "accounts": {"accounts": [{"account_id": "session-a"}]},
            "history:session-a:30": [{"ticket": 1}],
            "history:session-b:30": [{"ticket": 2}],
        }
        read_cache_lock = threading.RLock()

    class StateStore:
        def __init__(self):
            self.payload = {"accounts": {"session-a": {"account_id": "session-a"}}}

        def load(self):
            return self.payload

        def save(self, payload):
            self.payload = payload

    class Credentials:
        def __init__(self):
            self.deleted = []

        def delete(self, account_id):
            self.deleted.append(account_id)

    runtime = Runtime()
    state = StateStore()
    pool = FakePool(["session-a"])
    credentials = Credentials()

    monkeypatch.setattr(app_module, "_runtime", lambda: runtime)
    monkeypatch.setattr(app_module, "POOL", pool)
    monkeypatch.setattr(app_module, "STATE", state)
    monkeypatch.setattr(app_module, "CREDENTIALS", credentials)

    assert app_module.remove_account("session-a") == {"ok": True}
    assert pool.disconnected == ["session-a"]
    assert credentials.deleted == ["session-a"]
    assert "session-a" not in state.payload["accounts"]
    assert "positions" not in runtime.read_cache
    assert "accounts" not in runtime.read_cache
    assert "history:session-a:30" not in runtime.read_cache
    assert "history:session-b:30" in runtime.read_cache
