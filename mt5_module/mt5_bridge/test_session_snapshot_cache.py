from mt5_module.mt5_bridge import main as main_module


def setup_function():
    main_module._session_snapshot_cache.clear()
    main_module._stats_history_cache.clear()


def test_session_snapshot_collapses_duplicate_reads(monkeypatch):
    calls = {"count": 0}

    def fake_accounts():
        calls["count"] += 1
        return {"accounts": [{"login": 1}], "master": None, "slaves": []}

    monkeypatch.setattr(main_module, "current_workspace", lambda: "ws-test")
    monkeypatch.setattr(main_module.multi_account_client, "accounts", fake_accounts)

    first = main_module.session_snapshot()
    second = main_module.session_snapshot()

    assert first == second
    assert calls["count"] == 1


def test_session_snapshot_fresh_bypasses_cache(monkeypatch):
    calls = {"count": 0}
    def fake_accounts():
        calls["count"] += 1
        return {"accounts": [{"login": calls["count"]}]}

    monkeypatch.setattr(main_module, "current_workspace", lambda: "ws-test")
    monkeypatch.setattr(main_module.multi_account_client, "accounts", fake_accounts)

    first = main_module.session_snapshot()
    second = main_module.session_snapshot(fresh=True)

    assert first["accounts"][0]["login"] == 1
    assert second["accounts"][0]["login"] == 2
    assert calls["count"] == 2


def test_session_snapshot_uses_recent_cache_on_worker_error(monkeypatch):
    monkeypatch.setattr(main_module, "current_workspace", lambda: "ws-test")
    monkeypatch.setattr(
        main_module.multi_account_client,
        "accounts",
        lambda: {"accounts": [{"login": 7}], "master": None, "slaves": []},
    )
    seeded = main_module.session_snapshot()

    def fail():
        raise RuntimeError("temporary worker timeout")
    monkeypatch.setattr(main_module.multi_account_client, "accounts", fail)

    fallback = main_module.session_snapshot(fresh=True)

    assert fallback == seeded
    assert fallback.get("offline") is not True


def test_removed_account_history_is_purged(monkeypatch):
    state = {
        "history_archive": [
            {"account_login": 111, "ticket": 1},
            {"account_login": 222, "ticket": 2},
        ],
        "history_archive_full_sync_at": 123.0,
    }

    def fake_update(mutator):
        return mutator(state)

    monkeypatch.setattr(main_module, "current_workspace", lambda: "ws-test")
    monkeypatch.setattr(main_module, "update_state", fake_update)
    main_module._stats_history_cache["ws-test"] = {"loaded_at": 1.0}

    main_module._purge_removed_account_history(111)

    assert state["history_archive"] == [{"account_login": 222, "ticket": 2}]
    assert state["history_archive_full_sync_at"] == 0
    assert "ws-test" not in main_module._stats_history_cache


def test_positions_hide_unlinked_account_rows(monkeypatch):
    monkeypatch.setattr(
        main_module,
        "read_state",
        lambda: {"profiles": [{"login": 111}], "bots": []},
    )
    monkeypatch.setattr(
        main_module.multi_account_client,
        "request",
        lambda *args, **kwargs: {
            "positions": [
                {"account_login": 111, "ticket": 1},
                {"account_login": 222, "ticket": 2},
            ]
        },
    )
    monkeypatch.setattr(main_module, "_ui_position_row", lambda row, bots: row)

    assert main_module.positions() == [{"account_login": 111, "ticket": 1}]


def test_history_prunes_already_removed_accounts(monkeypatch):
    state = {
        "profiles": [{"login": 111}],
        "bots": [],
        "history_archive": [
            {"account_login": 111, "ticket": 1, "close_time": "2026-09-22T12:00:00+00:00"},
            {"account_login": 222, "ticket": 2, "close_time": "2026-09-22T12:00:00+00:00"},
        ],
        "history_archive_full_sync_at": 99999999999.0,
    }

    def fake_update(mutator):
        return mutator(state)

    monkeypatch.setattr(main_module, "read_state", lambda: state)
    monkeypatch.setattr(main_module, "update_state", fake_update)
    monkeypatch.setattr(main_module, "session_snapshot", lambda *args, **kwargs: {"accounts": []})
    monkeypatch.setattr(main_module, "current_workspace", lambda: "ws-test")

    rows = main_module.history(0)

    assert [row["account_login"] for row in rows] == [111]
    assert [row["account_login"] for row in state["history_archive"]] == [111]
