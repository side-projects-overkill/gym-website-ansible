"""Shared pytest fixtures.

Every test gets an isolated app instance backed by a temporary data
directory, so the whole suite runs fast and never touches real data.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gymapp import create_app  # noqa: E402
from gymapp import auth, db  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    app = create_app(data_dir=str(tmp_path / "data"))
    app.config["TESTING"] = True
    with app.app_context():
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(app, username="tester", password="password123"):
    """Create an active user (bypassing Telegram) and seed their metrics."""
    user_id = db.create_migrated_user(username, auth.hash_password(password))
    db.seed_default_metrics(user_id)
    return db.get_user(user_id)


@pytest.fixture()
def user(app):
    return make_user(app)


@pytest.fixture()
def logged_in(client, user):
    """A test client with a logged-in session for `user`."""
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    return client
