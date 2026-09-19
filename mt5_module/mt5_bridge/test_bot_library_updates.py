from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mt5_module"))
sys.path.insert(0, str(ROOT / "mt5_module" / "mt5_bridge"))

import main  # noqa: E402
from store import bot_library_revision  # noqa: E402


def test_running_ea_is_force_restarted_on_library_revision_change_even_with_open_trade(monkeypatch, tmp_path):
    ea_file = tmp_path / "updated.ex5"
    ea_file.write_bytes(b"updated-ea")
    state = {
        "bots": [{
            "id": 2000,
            "name": "Shared EA",
            "status": "running",
            "version": "2.0",
            "ea_storage_path": "updated.ex5",
            "ea_filename": "updated.ex5",
            "ea_sha256": "new-sha",
            "library_revision": "revision-new",
            "running_library_revision": "revision-old",
            "settings": {"magic_number": 9911},
        }]
    }
    assignment = {
        "bot_id": 2000,
        "status": "running",
        "open_positions": 3,
        "restart_request": {
            "bot_id": 2000,
            "account_login": 77123,
            "account_type": "live",
            "server": "Broker-Live",
            "symbol": "EURUSD",
            "timeframe": "M15",
            "ea_path": "old.ex5",
            "ea_filename": "old.ex5",
            "preset_path": None,
            "preset_filename": None,
            "allow_live": True,
            "allow_dll": False,
            "dll_required": False,
            "configured_magic": 9911,
        },
    }
    calls = []

    def request(path, method="GET", payload=None, timeout=4):
        calls.append((path, method, payload))
        if path == "/bots":
            return [assignment]
        if path == "/bots/2000/stop":
            return {"bot_id": 2000, "status": "stopped"}
        if path == "/bots/start":
            assert payload["account_login"] == 77123
            assert payload["symbol"] == "EURUSD"
            assert payload["timeframe"] == "M15"
            assert payload["allow_live"] is True
            assert payload["ea_path"] == str(ea_file.resolve())
            assert payload["ea_filename"] == "updated.ex5"
            return {
                **assignment,
                "status": "running",
                "process_id": 4321,
                "started_at": "now",
                "terminal_status": "online",
                "ea_verified": True,
                "ea_status": "active",
                "account_verified": True,
            }
        raise AssertionError(path)

    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "read_state", lambda: state)
    monkeypatch.setattr(main, "update_state", lambda mutator: mutator(state))
    monkeypatch.setattr(main, "set_workspace", lambda workspace_id: object())
    monkeypatch.setattr(main, "reset_workspace", lambda token: None)
    monkeypatch.setattr(main.ea_worker_client, "request", request)

    main._reconcile_library_updates("ws_update_test")

    assert [row[0] for row in calls] == ["/bots", "/bots/2000/stop", "/bots/start"]
    bot = state["bots"][0]
    assert bot["running_library_revision"] == "revision-new"
    assert bot["last_library_restart_from"] == "revision-old"
    assert bot["last_library_restart_to"] == "revision-new"
    assert bot["process_id"] == 4321


def test_first_revision_tracking_rollout_baselines_running_ea_without_restart(monkeypatch):
    state = {
        "bots": [{
            "id": 2001,
            "name": "Existing EA",
            "status": "running",
            "version": "1.0",
            "ea_sha256": "same-build",
            "library_revision": "baseline-revision",
            "settings": {},
        }]
    }
    assignment = {
        "bot_id": 2001,
        "status": "running",
        "open_positions": 2,
        "process_id": 99,
        "restart_request": {"bot_id": 2001},
    }
    calls = []

    def request(path, method="GET", payload=None, timeout=4):
        calls.append(path)
        if path == "/bots":
            return [assignment]
        raise AssertionError("Baseline rollout must not stop or restart an existing EA.")

    monkeypatch.setattr(main, "read_state", lambda: state)
    monkeypatch.setattr(main, "update_state", lambda mutator: mutator(state))
    monkeypatch.setattr(main, "set_workspace", lambda workspace_id: object())
    monkeypatch.setattr(main, "reset_workspace", lambda token: None)
    monkeypatch.setattr(main.ea_worker_client, "request", request)

    main._reconcile_library_updates("ws_baseline_test")

    assert calls == ["/bots"]
    assert state["bots"][0]["running_library_revision"] == "baseline-revision"


def test_library_revision_changes_when_strategy_hash_changes():
    old = bot_library_revision({"version": "1.0", "ea_sha256": "aaa"})
    new = bot_library_revision({"version": "1.0", "ea_sha256": "bbb"})
    assert old
    assert new
    assert old != new
