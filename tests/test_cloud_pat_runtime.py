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
