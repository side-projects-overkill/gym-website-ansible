from urllib.parse import quote_plus

from flask import Blueprint, redirect, render_template, session, url_for

from . import auth

bp = Blueprint("public", __name__)


@bp.app_template_filter("rest_seconds")
def rest_seconds(rest):
    from .workout_config import parse_rest_seconds
    return parse_rest_seconds(rest)


@bp.app_template_filter("youtube_search_url")
def youtube_search_url(query):
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


@bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("member.dashboard"))
    return render_template("landing.html")



@bp.route("/guide")
@auth.login_required
def guide():
    """The old standalone guide now lives inside Today (rules, rest timer,
    today's workout) - keep the URL working for bookmarks."""
    return redirect(url_for("member.dashboard"))
