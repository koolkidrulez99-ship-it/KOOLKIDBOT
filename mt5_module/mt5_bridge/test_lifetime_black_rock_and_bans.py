from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

import main
import store


def test_black_rock_system_preset_is_lifetime_mt5_ea():
    preset = next(row for row in store.SYSTEM_BOT_PRESETS if int(row["id"]) == 1011)
    assert preset["name"] == "BLACK ROCK"
    assert preset["engine"] == "ea"
    assert preset["lifetime_only"] is True
    assert preset["magic"] == 9122026

    bot = next(row for row in store._merge_system_bots([]) if int(row["id"]) == 1011)
    assert bot["native_engine"] is False
    assert bot["engine_type"] == "ea"
    assert bot["file_status"] == "ready"
    assert bot["ea_filename"] == "Black_Rock.ex5"
    assert bot["lifetime_only"] is True
    assert bot["timeframe"] == "M15"
    assert bot["bias_timeframe"] == "H4"


def test_black_rock_name_and_filename_detection():
    assert main._is_black_rock_bot({"name": "Black_Rock"}) is True
    assert main._is_black_rock_bot({"ea_filename": "BLACK ROCK.ex5"}) is True
    assert main._is_black_rock_bot({"name": "PRIMORDIAL BLACK"}) is False


def test_black_rock_is_hidden_for_testers_and_visible_for_lifetime(monkeypatch):
    rows = [
        {"id": 1, "name": "Black_Rock", "ea_filename": "Black_Rock.ex5", "lifetime_only": True},
        {"id": 2, "name": "DEAR BRUCE"},
    ]
    monkeypatch.setattr(main, "_current_workspace_is_lifetime", lambda: False)
    assert [row["id"] for row in main._visible_bots_for_current_user(rows)] == [2]
    with pytest.raises(HTTPException) as exc:
        main._require_black_rock_lifetime_access(rows[0])
    assert exc.value.status_code == 403

    monkeypatch.setattr(main, "_current_workspace_is_lifetime", lambda: True)
    assert [row["id"] for row in main._visible_bots_for_current_user(rows)] == [1, 2]
    main._require_black_rock_lifetime_access(rows[0])


def _write_users(path, users):
    path.write_text(json.dumps({"version": 1, "users": users}), encoding="utf-8")


def test_admin_can_ban_and_unban_user(monkeypatch, tmp_path):
    users_file = tmp_path / "users.json"
    _write_users(users_file, [{
        "id": "u1", "workspace_id": "ws_test", "username": "tester1",
        "role": "user", "access_tier": "tester",
    }])
    monkeypatch.setattr(main, "HUB_USERS_FILE", users_file)
    monkeypatch.setattr(main, "LEGACY_HUB_USERS_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(main, "_require_admin", lambda _request: {"username": "admin", "role": "admin"})

    banned = main.admin_user_ban("tester1", None, {"banned": True})
    assert banned["banned"] is True
    stored = json.loads(users_file.read_text(encoding="utf-8"))["users"][0]
    assert stored["banned"] is True
    assert stored["banned_by"] == "admin"

    unbanned = main.admin_user_ban("tester1", None, {"banned": False})
    assert unbanned["banned"] is False


def test_banned_user_cannot_log_in(monkeypatch, tmp_path):
    users_file = tmp_path / "users.json"
    salt = bytes.fromhex("00" * 16)
    _write_users(users_file, [{
        "id": "u1", "workspace_id": "ws_test", "username": "tester1",
        "role": "user", "access_tier": "tester", "banned": True,
        "password_salt": salt.hex(),
        "password_hash": main._password_hash("password123", salt),
    }])
    monkeypatch.setattr(main, "HUB_USERS_FILE", users_file)
    monkeypatch.setattr(main, "LEGACY_HUB_USERS_FILE", tmp_path / "legacy.json")

    with pytest.raises(HTTPException) as exc:
        main.hub_login(main.HubAuthPayload(username="tester1", password="password123"))
    assert exc.value.status_code == 403
    assert "banned" in str(exc.value.detail).lower()


def test_black_rock_resolver_uses_bundled_fallback(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    bundled_dir = tmp_path / "bundled_eas"
    data_dir.mkdir()
    bundled_dir.mkdir()
    fallback = bundled_dir / "Black_Rock.ex5"
    fallback.write_bytes(b"EX5-test")
    monkeypatch.setattr(store, "DATA_DIR", data_dir)
    monkeypatch.setattr(store, "ROOT", tmp_path)
    assert store.resolve_system_ea_file("Black_Rock.ex5") == fallback
