"""The app nav must link back to the static guide served at `/` by Apache,
so the guide and the app feel like one site."""

GUIDE_LINK = 'href="/guide"'


def test_logged_in_nav_links_to_guide(logged_in):
    resp = logged_in.get("/dashboard")
    assert resp.status_code == 200
    assert GUIDE_LINK in resp.get_data(as_text=True)


def test_anonymous_nav_links_to_guide(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert GUIDE_LINK in resp.get_data(as_text=True)
