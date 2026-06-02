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


def test_oauth_login_scope_includes_trade_and_account_manage():
    url = server._deriv_oauth_login_url("challenge", "state-value", "https://example.test/callback")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    scopes = set((query.get("scope") or [""])[0].split())

    assert "trade" in scopes
    assert "account_manage" in scopes


def test_ensure_oauth_demo_options_account_creates_when_missing(monkeypatch):
    create_calls = []

    def fake_create(access_token):
        create_calls.append(access_token)
        return {"account_id": "DOT777", "account_type": "demo", "currency": "USD", "is_virtual": True}

    def fake_fetch(access_token, allow_empty=False):
        assert allow_empty is True
        return [{"account_id": "DOT777", "account_type": "demo", "currency": "USD", "is_virtual": True}]

    monkeypatch.setattr(server, "_create_deriv_oauth_demo_options_account", fake_create)
    monkeypatch.setattr(server, "_fetch_deriv_oauth_accounts", fake_fetch)

    accounts = server._ensure_deriv_oauth_demo_options_account(
        "oauth-token",
        [{"account_id": "CR123", "account_type": "real", "currency": "USD"}],
    )

    assert create_calls == ["oauth-token"]
    assert any(account["account_id"] == "DOT777" for account in accounts)


def test_ensure_oauth_demo_options_account_skips_create_when_demo_exists(monkeypatch):
    create_calls = []
    monkeypatch.setattr(server, "_create_deriv_oauth_demo_options_account", lambda token: create_calls.append(token))

    accounts = server._ensure_deriv_oauth_demo_options_account(
        "oauth-token",
        [{"account_id": "DOT111", "account_type": "demo", "currency": "USD", "is_virtual": True}],
    )

    assert create_calls == []
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
