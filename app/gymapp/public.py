from urllib.parse import quote_plus

from flask import Blueprint, redirect, render_template, session, url_for

bp = Blueprint("public", __name__)


@bp.app_template_filter("youtube_search_url")
def youtube_search_url(query):
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


@bp.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("member.dashboard"))
    return render_template("landing.html")
