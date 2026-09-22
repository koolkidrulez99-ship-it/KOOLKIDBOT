from mt5_module.mt5_bridge import main as main_module


def setup_function():
    main_module._session_snapshot_cache.clear()


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
