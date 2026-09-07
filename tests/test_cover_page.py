import server


def test_anonymous_root_renders_cover_page(monkeypatch):
    monkeypatch.setattr(server, "login_required", lambda: False)

    with server.app.test_client() as client:
        response = client.get("/", follow_redirects=False)

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "KOOLKID AI" in body
    assert "TRADING ENGINE" in body
    assert 'href="/login"' in body
    assert 'href="/register"' in body
    assert "Five profiles" in body


def test_authenticated_root_keeps_existing_dashboard(monkeypatch):
    monkeypatch.setattr(server, "login_required", lambda: True)
    monkeypatch.setattr(server, "is_admin", lambda: False)
    monkeypatch.setattr(server, "render_template", lambda name, **context: name)

    with server.app.test_request_context("/"):
        assert server.index() == "index.html"


def test_login_page_remains_directly_available():
    with server.app.test_client() as client:
        response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200
    assert "Login - KoolKid Bot" in response.get_data(as_text=True)
