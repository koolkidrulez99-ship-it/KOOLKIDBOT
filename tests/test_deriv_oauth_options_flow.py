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
