"""Regression tests for auth + registration flows."""
from gymapp import db


def test_login_rejects_bad_credentials(client, user):
    r = client.post("/login", data={"username": "tester", "password": "wrong"})
    assert r.status_code == 200  # re-renders form with an error
    assert b"Invalid username" in r.data


def test_login_rejects_pending_user(client, app):
    db.create_pending_user("pendingperson")
    r = client.post("/login", data={"username": "pendingperson", "password": "x"})
    assert r.status_code == 200
    assert b"Invalid username" in r.data


def test_login_success_redirects_to_dashboard(client, user):
    r = client.post(
        "/login", data={"username": "tester", "password": "password123"}
    )
    assert r.status_code == 302
    assert "/dashboard" in r.headers["Location"]


def test_logout_clears_session(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    r = client.get("/logout")
    assert r.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_landing_redirects_logged_in_users_to_dashboard(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    r = client.get("/")
    assert r.status_code == 302
    assert "/dashboard" in r.headers["Location"]


def test_landing_anonymous(client):
    r = client.get("/")
    assert r.status_code == 200


def test_protected_routes_redirect_anonymous(client):
    for path in ("/dashboard", "/plan", "/tracker", "/attendance", "/walking", "/goals"):
        r = client.get(path)
        assert r.status_code == 302, path
        assert "/login" in r.headers["Location"], path
