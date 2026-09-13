from pathlib import Path

import server


ROOT = Path(__file__).resolve().parents[1]


def test_mt5_hub_is_public_and_serves_built_frontend():
    with server.app.test_client() as client:
        hub = client.get("/mt5-bot")
        assert hub.status_code == 200
        assert b'/mt5-bot/assets/' in hub.data


def test_public_homepage_has_mt5_button_and_disconnect_guard():
    source = (ROOT / "templates" / "cover.html").read_text(encoding="utf-8")
    login_at = source.index('href="/login">Log in</a>')
    mt5_at = source.index('href="/mt5-bot"')
    register_at = source.index('href="/register">Create account</a>')

    assert login_at < mt5_at < register_at
    assert ">MT5 BOT</a>" in source
    assert "sessionStorage.setItem('skipDisconnectOnce','1')" in source
