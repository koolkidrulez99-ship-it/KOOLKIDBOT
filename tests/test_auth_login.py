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


def test_login_reuses_client_id_hint_for_same_user(monkeypatch, tmp_path):
    db_path = tmp_path / "auth_login_client_hint.db"
    monkeypatch.setattr(server, "DB_BACKEND", "sqlite")
    monkeypatch.setattr(server, "DB_FILE", str(db_path))
    server.init_db()

    ok, _msg = server.create_user("HintUser", "Pass123!", grandfathered=1)
    assert ok is True

    hinted_client_id = "client-hint-123"
    monkeypatch.setattr(
        server,
        "load_trade_runtime",
        lambda client_id, **kwargs: {"_stored_username": "hintuser"} if client_id == hinted_client_id else None,
    )

    with server.app.test_client() as client:
        response = client.post(
            "/login",
            data={"username": "HintUser", "password": "Pass123!", "client_id_hint": hinted_client_id},
            follow_redirects=False,
        )
        with client.session_transaction() as sess:
            assert sess["client_id"] == hinted_client_id

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
