from urllib.parse import quote_plus

from flask import Blueprint, jsonify, redirect, render_template, session, url_for

from . import auth

bp = Blueprint("public", __name__)


@bp.app_template_filter("youtube_search_url")
def youtube_search_url(query):
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


@bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("member.dashboard"))
    return render_template("landing.html")


@bp.route("/session")
def session_state():
    """Login state for the static guide's nav (it lives outside Flask).

    Deliberately public and minimal: only whether you're logged in and your
    username. Never cached, so a logout is reflected immediately.
    """
    user = auth.current_user()
    payload = {"logged_in": True, "username": user["username"]} if user else {"logged_in": False}
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-store"
    return resp
