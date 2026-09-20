import server


def test_master_home_links_to_both_existing_products():
    client = server.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"One account. Two trading platforms." in response.data
    assert b'href="/deriv-bot"' in response.data
    assert b'href="/mt5-bot"' in response.data
    assert b"https://t.me/jordibrown" in response.data
    assert b"https://wa.me/qr/XFJMRUGZX5SBF1" in response.data


def test_deriv_bot_keeps_the_existing_public_cover():
    client = server.app.test_client()

    response = client.get("/deriv-bot")

    assert response.status_code == 200
    assert b"THE KOOLKID PRO EXPERIENCE" in response.data
    assert b'id="coverHero"' in response.data
