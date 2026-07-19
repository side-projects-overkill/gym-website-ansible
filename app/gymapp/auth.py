"""Multi-user authentication, backed by the `users` table in SQLite.

Session state is just `session['user_id']`. Accounts move through
`pending_telegram -> pending_password -> active`; only `active` accounts
can log in with a password.
"""
import os
import secrets
from functools import wraps

from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


def current_user():
    """Return the users row for the logged-in session, or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.get_user(user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("member.login"))
        return view(*args, **kwargs)

    return wrapped


def hash_password(password):
    return generate_password_hash(password)


def verify_password(user_row, password):
    if not user_row or not user_row["password_hash"]:
        return False
    return check_password_hash(user_row["password_hash"], password)


def check_login(username, password):
    """Look up `username`, verify it's active with a matching password.
    Returns the user row on success, None otherwise."""
    user = db.get_user_by_username(username)
    if not user:
        return None
    if user["status"] != "active":
        return None
    if not verify_password(user, password):
        return None
    return user


def get_or_create_secret_key(data_dir):
    path = os.path.join(data_dir, "secret_key.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)
    os.chmod(path, 0o600)
    return key
