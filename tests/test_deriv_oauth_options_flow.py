import json
import urllib.parse

import server


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_oauth_login_scope_uses_trade_only():
    url = server._deriv_oauth_login_url("challenge", "state-value", "https://example.test/callback")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    scopes = set((query.get("scope") or [""])[0].split())

    assert "trade" in scopes
    assert "account_manage" not in scopes


def test_oauth_accounts_are_read_with_get_only(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "DERIV_ACCOUNTS_URL", "https://example.test/trading/v1/options/accounts")

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["authorization"] = req.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse({"data": [{"account_id": "DOT111", "account_type": "demo", "currency": "USD"}]})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    accounts = server._fetch_deriv_oauth_accounts("oauth-token")

    assert captured["url"].endswith("/trading/v1/options/accounts")
    assert captured["method"] == "GET"
    assert captured["authorization"] == "Bearer oauth-token"
    assert accounts[0]["account_id"] == "DOT111"


def test_oauth_options_otp_uses_selected_account_and_bearer_headers(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        server,
        "DERIV_OPTIONS_OTP_ENDPOINT_TEMPLATE",
        "https://example.test/trading/v1/options/accounts/{account_id}/otp",
    )

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["authorization"] = req.get_header("Authorization")
        captured["headers"] = dict(req.headers)
        captured["data"] = req.data
        captured["timeout"] = timeout
        return FakeResponse({"data": {"url": "wss://otp.example/socket"}})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    url = server._request_oauth_options_ws_url("cid-oauth", "secret-oauth-token", "DOT123", "oauth-app")

    assert url == "wss://otp.example/socket"
    assert captured["url"].endswith("/trading/v1/options/accounts/DOT123/otp")
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer secret-oauth-token"
    assert any(key.lower() == "deriv-app-id" and value == "oauth-app" for key, value in captured["headers"].items())
    assert captured["data"] == b""


def test_pat_accounts_are_read_with_pat_app_id_and_bearer_headers(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "DERIV_PAT_APP_ID", "pat-app")
    monkeypatch.setattr(server, "DERIV_APP_ID", "legacy-app")
    monkeypatch.setattr(server, "DERIV_ACCOUNTS_URL", "https://example.test/trading/v1/options/accounts")

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["authorization"] = req.get_header("Authorization")
        captured["headers"] = dict(req.headers)
        captured["timeout"] = timeout
        return FakeResponse({"data": [{"account_id": "DOT222", "account_type": "demo", "currency": "USD"}]})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    accounts = server._fetch_deriv_pat_accounts("pat-secret-token")

    assert captured["url"].endswith("/trading/v1/options/accounts")
    assert captured["method"] == "GET"
    assert captured["authorization"] == "Bearer pat-secret-token"
    assert any(key.lower() == "deriv-app-id" and value == "pat-app" for key, value in captured["headers"].items())
    assert accounts[0]["account_id"] == "DOT222"


def test_pat_app_id_must_not_reuse_legacy_app_id(monkeypatch):
    monkeypatch.setattr(server, "DERIV_PAT_APP_ID", "same-app")
    monkeypatch.setattr(server, "DERIV_APP_ID", "same-app")

    try:
        server._get_deriv_pat_app_id()
    except RuntimeError as exc:
        assert "separate PAT-type" in str(exc)
    else:
        raise AssertionError("Expected DERIV_PAT_APP_ID reuse to fail")


def test_pat_options_otp_uses_selected_account_and_pat_app_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(server, "DERIV_PAT_APP_ID", "pat-app")
    monkeypatch.setattr(server, "DERIV_APP_ID", "legacy-app")
    monkeypatch.setattr(
        server,
        "DERIV_OPTIONS_OTP_ENDPOINT_TEMPLATE",
        "https://example.test/trading/v1/options/accounts/{account_id}/otp",
    )

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["authorization"] = req.get_header("Authorization")
        captured["headers"] = dict(req.headers)
        captured["data"] = req.data
        captured["timeout"] = timeout
        return FakeResponse({"data": {"url": "wss://otp.example/socket"}})

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)

    url = server._request_pat_options_ws_url("cid-pat", "pat-secret-token", "DOT456")

    assert url == "wss://otp.example/socket"
    assert captured["url"].endswith("/trading/v1/options/accounts/DOT456/otp")
    assert captured["method"] == "POST"
    assert captured["authorization"] == "Bearer pat-secret-token"
    assert any(key.lower() == "deriv-app-id" and value == "pat-app" for key, value in captured["headers"].items())
    assert captured["data"] == b""


def test_api_connection_status_returns_safe_pat_switch_accounts(monkeypatch):
    state = server._build_default_client_state()
    state.update({
        "api_token": "pat-secret-token",
        "api_token_type": "pat",
        "deriv_app_id": "pat-app",
        "ws_connected": True,
        "ws_transport_connected": True,
        "ws": object(),
        "pat_options_account_id": "DOT111",
        "options_account_id": "DOT111",
        "deriv_account_id": "DOT111",
        "loginid": "DOT111",
        "pat_accounts": [
            {"account_id": "DOT111", "account_type": "demo", "currency": "USD"},
            {"account_id": "CR222", "account_type": "real", "currency": "USD"},
        ],
    })
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-pat-status", state))
    monkeypatch.setattr(server, "_check_ws_connect_timeout", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_has_active_tick_stream_warmup", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(server, "_is_ws_stale", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(server, "_get_tick_stream_health", lambda *_args, **_kwargs: {"tick_stream_healthy": True})
    monkeypatch.setattr(server, "get_user_license_context", lambda: {})

    with server.app.test_request_context("/api_connection_status"):
        response = server.api_connection_status()

    data = response.get_json()
    encoded = json.dumps(data)
    assert data["connection_mode"] == "pat"
    assert data["pat_account_switch_available"] is True
    assert data["pat_current_account_id"] == "DOT111"
    assert [account["account_id"] for account in data["pat_accounts"]] == ["DOT111", "CR222"]
    assert "pat-secret-token" not in encoded


def test_pat_authenticated_connection_event_includes_switch_accounts(monkeypatch):
    emitted = []
    sent = []
    state = server._build_default_client_state()
    state.update({
        "api_token": "pat-secret-token",
        "api_token_type": "pat",
        "deriv_app_id": "pat-app",
        "pat_options_account_id": "DOT111",
        "options_account_id": "DOT111",
        "deriv_account_id": "DOT111",
        "pat_accounts": [
            {"account_id": "DOT111", "account_type": "demo", "currency": "USD"},
            {"account_id": "CR222", "account_type": "real", "currency": "USD"},
        ],
    })

    class DummyWs:
        def send(self, payload):
            sent.append(payload)

    monkeypatch.setattr(server, "_restore_required_tick_subscriptions", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_get_tick_stream_health", lambda *_args, **_kwargs: {"tick_stream_healthy": True})
    monkeypatch.setattr(server, "_emit_balance_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "emit_profile_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "request_human_seed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(server, "_uses_new_deriv_trade_api", lambda _state: False)
    monkeypatch.setattr(server.socketio, "emit", lambda event, payload=None, room=None: emitted.append((event, payload, room)))

    server._complete_deriv_authenticated_session(
        "cid-pat-auth-event",
        state,
        DummyWs(),
        "DOT111",
        42.0,
        source="pat_options_balance",
    )

    connection_payload = next(payload for event, payload, _room in emitted if event == "connection_status")
    encoded = json.dumps(connection_payload)
    assert connection_payload["connected"] is True
    assert connection_payload["connection_mode"] == "pat"
    assert connection_payload["pat_account_switch_available"] is True
    assert connection_payload["pat_current_account_id"] == "DOT111"
    assert [account["account_id"] for account in connection_payload["pat_accounts"]] == ["DOT111", "CR222"]
    assert "pat-secret-token" not in encoded
    assert sent == [json.dumps({"balance": 1, "subscribe": 1})]


def test_switch_pat_account_rejects_oauth_session(monkeypatch):
    state = server._build_default_client_state()
    state.update({
        "api_token": "oauth-secret-token",
        "api_token_type": "oauth",
        "ws_connected": True,
        "ws": object(),
        "oauth_options_account_id": "DOT111",
    })
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-oauth", state))

    with server.app.test_request_context("/switch_pat_account", method="POST", json={"account_id": "CR222"}):
        response, status = server.switch_pat_account()

    data = response.get_json()
    assert status == 409
    assert "PAT connections" in data["message"]


def test_switch_pat_account_uses_stored_token_and_selected_account(monkeypatch):
    captured = {}
    state = server._build_default_client_state()
    state.update({
        "api_token": "pat-secret-token",
        "api_token_type": "pat",
        "deriv_app_id": "pat-app",
        "ws_connected": True,
        "ws": object(),
        "pat_options_account_id": "DOT111",
        "options_account_id": "DOT111",
        "deriv_account_id": "DOT111",
        "pat_accounts": [
            {"account_id": "DOT111", "account_type": "demo", "currency": "USD"},
            {"account_id": "CR222", "account_type": "real", "currency": "USD"},
        ],
    })
    accounts = [
        {"account_id": "DOT111", "account_type": "demo", "currency": "USD"},
        {"account_id": "CR222", "account_type": "real", "currency": "USD"},
    ]
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-pat-switch", state))

    def fake_fetch(token, app_id=None):
        captured["fetch"] = (token, app_id)
        return accounts

    monkeypatch.setattr(server, "_fetch_deriv_pat_accounts", fake_fetch)

    def fake_start(cid, live_state, token, token_type, account_id, reason, app_id=None):
        captured["start"] = (cid, token, token_type, account_id, reason, app_id)
        live_state["api_token_type"] = token_type
        live_state["pat_options_account_id"] = account_id
        live_state["options_account_id"] = account_id

    monkeypatch.setattr(server, "_start_deriv_connection_for_state", fake_start)

    with server.app.test_request_context("/switch_pat_account", method="POST", json={"account_id": "CR222"}):
        response = server.switch_pat_account()

    data = response.get_json()
    encoded = json.dumps(data)
    assert data["status"] == "switching"
    assert data["account_id"] == "CR222"
    assert captured["fetch"] == ("pat-secret-token", "pat-app")
    assert captured["start"] == ("cid-pat-switch", "pat-secret-token", "pat", "CR222", "pat_account_switch", "pat-app")
    assert "pat-secret-token" not in encoded


def test_switch_pat_account_blocks_unknown_account(monkeypatch):
    state = server._build_default_client_state()
    state.update({
        "api_token": "pat-secret-token",
        "api_token_type": "pat",
        "deriv_app_id": "pat-app",
        "ws_connected": True,
        "ws": object(),
        "pat_options_account_id": "DOT111",
        "options_account_id": "DOT111",
    })
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-pat-unknown", state))
    monkeypatch.setattr(server, "_fetch_deriv_pat_accounts", lambda token, app_id=None: [
        {"account_id": "DOT111", "account_type": "demo", "currency": "USD"},
    ])

    with server.app.test_request_context("/switch_pat_account", method="POST", json={"account_id": "CR999"}):
        response, status = server.switch_pat_account()

    assert status == 400
    assert "unavailable" in response.get_json()["message"]


def test_switch_pat_account_blocks_open_contract(monkeypatch):
    state = server._build_default_client_state()
    state.update({
        "api_token": "pat-secret-token",
        "api_token_type": "pat",
        "deriv_app_id": "pat-app",
        "ws_connected": True,
        "ws": object(),
        "pat_options_account_id": "DOT111",
        "options_account_id": "DOT111",
        "human_pending_contracts": {"123": {"contract_id": "123", "status": "OPEN"}},
    })
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "get_client_state", lambda: ("cid-pat-open", state))

    with server.app.test_request_context("/switch_pat_account", method="POST", json={"account_id": "CR222"}):
        response, status = server.switch_pat_account()

    assert status == 409
    assert "settle" in response.get_json()["message"]
