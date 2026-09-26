import json

import server


class _FakeSocket:
    def __init__(self):
        self.messages = []

    def send(self, value):
        self.messages.append(json.loads(value))


def test_cloud_runtime_preserves_pat_identity(monkeypatch):
    source = server._build_default_client_state()
    source.update({
        "username": "alice",
        "api_token": "secret-pat",
        "api_token_type": "pat",
        "deriv_account_id": "VRTC123",
        "options_account_id": "VRTC123",
        "deriv_app_id": server.DERIV_PAT_APP_ID,
    })
    cloud_key = "user:alice:account:vrtc123"
    runtime_cid = server._cloud_runtime_client_id(cloud_key)
    server.clients.pop(runtime_cid, None)
    starts = []
    monkeypatch.setattr(server, "_start_ws_worker_thread", lambda cid, state, reason=None: starts.append((cid, reason)))

    assert server._ensure_cloud_runtime_for_state(source, cloud_key, {"current_market": "R_10"}) is True

    runtime = server.clients[runtime_cid]
    assert runtime["api_token_type"] == "pat"
    assert runtime["deriv_account_id"] == "VRTC123"
    assert runtime["deriv_app_id"] == server.DERIV_PAT_APP_ID
    assert starts == [(runtime_cid, "cloud_under9_runtime")]
    server.clients.pop(runtime_cid, None)


def test_cloud_accumulator_pat_uses_proposal_id(monkeypatch):
    state = server._build_default_client_state()
    state.update({
        "ws_connected": True,
        "ws": _FakeSocket(),
        "api_token_type": "pat",
        "current_symbol": "R_10",
    })
    server.clients["cloud-test"] = state
    captured = {}
    monkeypatch.setattr(server, "resolve_new_api_symbol", lambda *args, **kwargs: ("R_10", None))

    def proposal(_client_id, _state, payload, timeout_sec=5.0):
        captured["payload"] = payload
        return {"id": "cloud-proposal", "ask_price": 1.0}, None

    monkeypatch.setattr(server, "_request_digit_proposal_for_buy", proposal)

    ok, _message = server._send_cloud_accumulator_buy(
        "cloud-test",
        stake=1,
        symbol="R_10",
        growth_rate=0.05,
        signal_id="signal-1",
        hold_ticks=2,
    )

    assert ok is True
    assert captured["payload"]["underlying_symbol"] == "R_10"
    assert captured["payload"]["growth_rate"] == 0.05
    assert state["ws"].messages[-1]["buy"] == "cloud-proposal"
    assert next(iter(state["req_meta"].values()))["exit_ticks"] == 2
    server.clients.pop("cloud-test", None)


def test_cloud_identity_uses_preserved_session_key_after_pat_disconnect():
    state = server._build_default_client_state()
    state.update({
        "username": "alice",
        "cloud_session_key": "user:alice:token:abc123",
        "api_token": "",
        "api_token_type": "none",
        "deriv_account_id": "",
    })

    status_identity = server._cloud_identity_for_state(state, require_token=False)
    protected_identity = server._cloud_identity_for_state(state, require_token=True)

    assert status_identity["key"] == "user:alice:token:abc123"
    assert status_identity["token_verified"] is False
    assert status_identity["identity_type"] == "preserved_cloud_session"
    assert protected_identity["key"] == ""


def test_pat_disconnect_preserves_cloud_key_and_does_not_kill_cloud_runtime(monkeypatch):
    browser_cid = "browser-cloud-disconnect"
    cloud_key = "user:alice:token:abc123"
    runtime_cid = server._cloud_runtime_client_id(cloud_key)

    browser = server._build_default_client_state()
    browser.update({
        "username": "alice",
        "cloud_session_key": cloud_key,
        "api_token": "pat-secret",
        "api_token_type": "pat",
        "deriv_account_id": "VRTC123",
    })
    runtime = server._build_default_client_state()
    runtime.update({
        "username": cloud_key,
        "cloud_runtime": True,
        "cloud_session_key": cloud_key,
        "api_token": "pat-secret",
        "api_token_type": "pat",
        "deriv_account_id": "VRTC123",
    })
    server.clients[browser_cid] = browser
    server.clients[runtime_cid] = runtime

    monkeypatch.setattr(server.cloud_manager, "has_session", lambda key: key == cloud_key)
    monkeypatch.setattr(server, "_cleanup_client_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_hard_stop_all_strategies", lambda *args, **kwargs: None)

    try:
        server.disconnect_client(browser_cid, reason="manual_disconnect", emit=False)

        reset = server.clients[browser_cid]
        assert reset["api_token"] == ""
        assert reset["ws_connected"] is False
        assert reset["cloud_session_key"] == cloud_key
        assert reset["username"] == "alice"
        assert server.clients[runtime_cid] is runtime
        assert runtime["cloud_runtime"] is True
        assert runtime["api_token"] == "pat-secret"
    finally:
        server.clients.pop(browser_cid, None)
        server.clients.pop(runtime_cid, None)


def test_logout_does_not_preserve_cloud_session_key(monkeypatch):
    cid = "browser-cloud-logout"
    state = server._build_default_client_state()
    state.update({
        "username": "alice",
        "cloud_session_key": "user:alice:token:abc123",
        "api_token": "pat-secret",
        "api_token_type": "pat",
    })
    server.clients[cid] = state
    monkeypatch.setattr(server.cloud_manager, "has_session", lambda key: True)
    monkeypatch.setattr(server, "_cleanup_client_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(server, "_hard_stop_all_strategies", lambda *args, **kwargs: None)

    try:
        server.disconnect_client(cid, reason="logout", emit=False)
        assert server.clients[cid].get("cloud_session_key") in (None, "")
    finally:
        server.clients.pop(cid, None)


def _build_cloud_route_test_app(identity_provider, manager):
    from flask import Flask
    from cloud_routes import register_cloud_routes

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "cloud-test-secret"
    state = {}
    register_cloud_routes(
        app,
        cloud_manager=manager,
        login_required=lambda: True,
        get_client_state=lambda: ("cid-cloud-route", state),
        ensure_tick_subscription=lambda *args, **kwargs: True,
        get_cloud_identity=identity_provider,
        can_use_cloud_profile=lambda: True,
    )
    return app


def test_cloud_status_falls_back_to_signed_session_key_after_browser_runtime_is_gone():
    cloud_key = "user:alice:token:abc123"

    class Manager:
        def __init__(self):
            self.status_keys = []

        def status(self, key):
            self.status_keys.append(key)
            return {
                "status": "success",
                "running": True,
                "cloud_enabled": True,
                "cloud_status": "Running",
                "settings": {},
                "allowed_markets": ["R_75"],
                "current_market": "R_75",
                "current_stake": 1.0,
                "session_profit": 0.0,
                "reinvest_step": 0,
                "wins": 0,
                "losses": 0,
            }

    manager = Manager()
    app = _build_cloud_route_test_app(
        lambda state, require_token=False: {
            "key": "",
            "token_verified": False,
            "requires_token_verification": True,
        },
        manager,
    )

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = "alice"
            sess["cloud_session_key"] = cloud_key

        response = client.get("/cloud/under9/status")
        payload = response.get_json()

    assert response.status_code == 200
    assert manager.status_keys == [cloud_key]
    assert payload["running"] is True
    assert payload["token_verified"] is False
    assert payload["cloud_identity_type"] == "preserved_cloud_session"


def test_verified_cloud_identity_is_saved_in_signed_session_for_later_disconnect():
    cloud_key = "user:alice:token:abc123"

    class Manager:
        def status(self, key):
            return {
                "status": "success",
                "running": True,
                "cloud_enabled": True,
                "cloud_status": "Running",
                "settings": {},
                "allowed_markets": ["R_75"],
                "current_market": "R_75",
                "current_stake": 1.0,
                "session_profit": 0.0,
                "reinvest_step": 0,
                "wins": 0,
                "losses": 0,
            }

    app = _build_cloud_route_test_app(
        lambda state, require_token=False: {
            "key": cloud_key,
            "token_verified": True,
            "requires_token_verification": False,
            "identity_type": "token_fingerprint",
        },
        Manager(),
    )

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = "alice"

        response = client.get("/cloud/under9/status")
        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert sess["cloud_session_key"] == cloud_key
