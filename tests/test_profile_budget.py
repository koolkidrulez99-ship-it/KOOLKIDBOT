from types import SimpleNamespace

import pytest

import server


def test_profile_budget_snapshot_uses_budget_as_display_balance():
    state = {
        "balance": 100.0,
        "active_profile": "UNCHAIN",
        "profile_budgets": {
            "UNCHAIN": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
    }

    snapshot = server._profile_budget_snapshot(state, "UNCHAIN")

    assert snapshot["enabled"] is True
    assert snapshot["configured_budget"] == 20.0
    assert snapshot["display_balance"] == 20.0
    assert snapshot["total_balance"] == 100.0


def test_profile_budget_reservation_releases_and_applies_profit():
    state = {
        "profile_budgets": {
            "NTT": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
    }

    ok, _msg, reservation = server._reserve_profile_budget(state, "NTT", 5.0)
    assert ok is True
    assert state["profile_budgets"]["NTT"]["reserved"] == 5.0

    server._settle_profile_budget_reservation(state, reservation, 2.5)

    assert state["profile_budgets"]["NTT"]["reserved"] == 0.0
    assert state["profile_budgets"]["NTT"]["realized_pnl"] == 2.5


def test_profile_budget_reservation_release_is_idempotent():
    state = {
        "profile_budgets": {
            "NTT": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
    }

    ok, _msg, reservation = server._reserve_profile_budget(state, "NTT", 5.0)
    assert ok is True
    assert state["profile_budgets"]["NTT"]["reserved"] == 5.0

    server._release_profile_budget_reservation(state, reservation)
    server._release_profile_budget_reservation(state, reservation)

    assert state["profile_budgets"]["NTT"]["reserved"] == 0.0


def test_profile_budget_reservation_settle_is_idempotent():
    state = {
        "profile_budgets": {
            "NTT": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
    }

    ok, _msg, reservation = server._reserve_profile_budget(state, "NTT", 0.35)
    assert ok is True

    server._settle_profile_budget_reservation(state, reservation, -0.35)
    server._settle_profile_budget_reservation(state, reservation, -0.35)

    assert state["profile_budgets"]["NTT"]["reserved"] == 0.0
    assert state["profile_budgets"]["NTT"]["realized_pnl"] == -0.35


def test_send_buy_with_profile_blocks_trade_above_profile_budget(monkeypatch):
    class DummyWs:
        def send(self, _payload):
            raise AssertionError("ws.send should not be called when budget blocks the trade")

    strategy = SimpleNamespace(
        enforce_tp_sl=lambda: None,
        risk_block_reason=None,
    )
    state = {
        "ws_connected": True,
        "ws": DummyWs(),
        "balance": 100.0,
        "active_profile": "KOOLKID",
        "req_meta": {},
        "profile_budgets": {
            "KOOLKID": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
        "strategies": {"KOOLKID": strategy},
    }

    monkeypatch.setitem(server.clients, "cid-budget", state)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    ok, message = server.send_buy_with_profile(
        "cid-budget",
        "KOOLKID",
        "OVER",
        25.0,
        "R_10",
        5,
    )

    assert ok is False
    assert "budget" in message.lower()
    assert state["profile_budgets"]["KOOLKID"]["reserved"] == 0.0


def test_unchain_pair_balance_respects_profile_budget():
    state = {
        "balance": 100.0,
        "profile_budgets": {
            "UNCHAIN": {"amount": 20.0, "realized_pnl": 0.0, "reserved": 0.0},
        },
    }

    ok, message, _plan, total_stake, available = server._check_unchain_pair_balance(
        state,
        [("HIGHER", 12.0, "+0.12"), ("LOWER", 12.0, "-0.12")],
        failure_prefix="Trade failed",
    )

    assert ok is False
    assert total_stake == 24.0
    assert available == 20.0
    assert "budget" in message.lower()


def test_profile_budget_route_updates_display_balance(monkeypatch):
    state = {
        "balance": 100.0,
        "active_profile": "UNCHAIN",
        "profile_budgets": server._new_profile_budget_map(),
    }

    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-budget-route", state))
    monkeypatch.setattr(server, "send_stats_update", lambda _cid: None)
    monkeypatch.setattr(server.socketio, "emit", lambda *args, **kwargs: None)

    with server.app.test_client() as client:
        response = client.post("/profile_budget", json={"profile": "UNCHAIN", "budget": 20})

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["display_balance"] == 20.0
    assert payload["total_balance"] == 100.0
    assert payload["active_profile_budget"]["enabled"] is True
    assert payload["active_profile_budget"]["configured_budget"] == 20.0


def test_cloud_budget_is_saved_with_the_cloud_session(monkeypatch):
    state = {
        "profile_budgets": {
            "CLOUD": {"amount": 75.0, "realized_pnl": 4.25, "reserved": 0.0},
        },
    }
    saved = {}
    monkeypatch.setattr(server, "_cloud_key_for_state", lambda _state: "cloud-user")
    monkeypatch.setattr(server.cloud_manager, "update_settings", lambda key, settings: saved.update({"key": key, **settings}))

    server._persist_cloud_budget(state)

    assert saved == {
        "key": "cloud-user",
        "profile_budget": 75.0,
        "profile_budget_realized_pnl": 4.25,
    }


def test_cloud_budget_restores_from_cloud_settings(monkeypatch):
    state = {"profile_budgets": server._new_profile_budget_map()}
    monkeypatch.setattr(server, "_estimate_profile_open_budget_exposure", lambda *_args: 0.0)

    server._restore_cloud_budget_from_status(state, {
        "settings": {"profile_budget": 50.0, "profile_budget_realized_pnl": -2.5},
    })

    assert state["profile_budgets"]["CLOUD"] == {
        "amount": 50.0,
        "realized_pnl": -2.5,
        "reserved": 0.0,
    }


def test_cloud_history_snapshot_uses_persisted_cloud_rows(monkeypatch):
    state = server._build_default_client_state()
    state["username"] = "alice"
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-cloud-history", state))
    monkeypatch.setattr(server, "_cloud_key_for_state", lambda _state: "cloud-user")
    monkeypatch.setattr(server.cloud_manager, "history", lambda _key: [{
        "contract_id": "cloud-1",
        "time": "2026-09-22 12:00:00",
        "trade_type": "under9",
        "market": "R_25",
        "stake": 1.0,
        "profit": 0.8,
        "result": "WIN",
    }])

    with server.app.test_client() as client:
        response = client.get("/profile_history_snapshot?profile=CLOUD")

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["profiles"]["CLOUD"][0]["contract_id"] == "cloud-1"
    assert payload["profiles"]["CLOUD"][0]["symbol"] == "R_25"
    assert payload["profiles"]["CLOUD"][0]["type"] == "under9"


def test_cloud_stats_use_the_same_persisted_history_profit_as_trade_history(monkeypatch):
    emitted = []
    state = {
        "active_profile": "CLOUD",
        "cloud_session_key": "cloud-user",
    }
    monkeypatch.setitem(server.clients, "cid-cloud-stats", state)
    monkeypatch.setattr(server.cloud_manager, "status", lambda _key: {
        "wins": 2,
        "losses": 1,
        "daily_profit": 99.0,
        "history_profit": 1.6,
        "running": True,
    })
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload, room=None: emitted.append((event, payload, room)))

    try:
        server.send_stats_update("cid-cloud-stats")
    finally:
        server.clients.pop("cid-cloud-stats", None)

    stats = [payload for event, payload, _room in emitted if event == "stats_update"]
    assert len(stats) == 1
    assert stats[0]["net_pnl"] == pytest.approx(1.6)
