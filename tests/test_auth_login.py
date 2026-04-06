import server


def test_verify_user_accepts_case_insensitive_username(monkeypatch, tmp_path):
    db_path = tmp_path / "auth_login_case.db"
    monkeypatch.setattr(server, "DB_BACKEND", "sqlite")
    monkeypatch.setattr(server, "DB_FILE", str(db_path))
    server.init_db()

    ok, _msg = server.create_user("AliceCase", "Pass123!", grandfathered=1)
    assert ok is True

    assert server.verify_user("alicecase", "Pass123!") is True
    assert server.verify_user("ALICECASE", "Pass123!") is True


def test_login_accepts_email_identifier(monkeypatch, tmp_path):
    db_path = tmp_path / "auth_login_email.db"
    monkeypatch.setattr(server, "DB_BACKEND", "sqlite")
    monkeypatch.setattr(server, "DB_FILE", str(db_path))
    server.init_db()

    ok, _msg = server.create_user("MailUser", "Pass123!", email="mailuser@example.com", grandfathered=1)
    assert ok is True

    with server.app.test_client() as client:
        response = client.post(
            "/login",
            data={"username": "MAILUSER@EXAMPLE.COM", "password": "Pass123!"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
