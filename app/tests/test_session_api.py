"""/session lets the static guide (served by Apache, outside Flask) show the
right nav. It must expose only login state + username, never be cached, and
work without auth."""


def test_session_anonymous(client):
    r = client.get("/session")
    assert r.status_code == 200
    assert r.get_json() == {"logged_in": False}
    assert "no-store" in r.headers.get("Cache-Control", "")


def test_session_logged_in(logged_in, user):
    r = logged_in.get("/session")
    assert r.status_code == 200
    assert r.get_json() == {"logged_in": True, "username": user["username"]}
    assert "no-store" in r.headers.get("Cache-Control", "")
