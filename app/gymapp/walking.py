"""Walking tracker check-in routes - mirrors `gymapp.attendance`, but for
walks instead of gym visits, with optional distance/duration per entry.

Blueprint name "walking", no url_prefix.
"""
from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import auth, db, localtime

bp = Blueprint("walking", __name__)


def _redirect_target():
    """Mirror attendance.py's `redirect_to` hidden-field pattern so a
    dashboard widget can land the user back there after a check-in."""
    if request.form.get("redirect_to") == "dashboard":
        return "member.dashboard"
    return "walking.walking"


@bp.route("/walking")
@auth.login_required
def walking():
    current_user = auth.current_user()
    user_id = current_user["id"]
    today_date = localtime.today()
    today = today_date.isoformat()

    recent_walks = db.list_recent_walks(user_id, limit=60)
    walked_today = any(row["walk_date"] == today for row in recent_walks)

    since_7d = (today_date - timedelta(days=6)).isoformat()
    since_30d = (today_date - timedelta(days=29)).isoformat()

    stats = {
        "total": db.total_walk_count(user_id),
        "last_7_days": db.count_walks_since(user_id, since_7d),
        "last_30_days": db.count_walks_since(user_id, since_30d),
    }

    return render_template(
        "member/walking.html",
        recent_walks=recent_walks,
        walked_today=walked_today,
        stats=stats,
        today=today,
        current_user=current_user,
    )


@bp.route("/walking/checkin", methods=["POST"])
@auth.login_required
def checkin():
    current_user = auth.current_user()
    user_id = current_user["id"]
    today = localtime.today().isoformat()

    if db.checkin_walk(user_id, today):
        flash("Walk logged for today. Nice work!", "success")
    else:
        flash("Already logged a walk today.", "error")

    return redirect(url_for(_redirect_target()))


@bp.route("/walking/add", methods=["POST"])
@auth.login_required
def add():
    current_user = auth.current_user()
    user_id = current_user["id"]
    walk_date = request.form.get("walk_date", "").strip()
    raw_distance = request.form.get("distance_km", "").strip()
    raw_duration = request.form.get("duration_min", "").strip()
    note = request.form.get("note", "").strip()

    try:
        date.fromisoformat(walk_date)
    except ValueError:
        flash("Please provide a valid date.", "error")
        return redirect(url_for(_redirect_target()))

    if walk_date > localtime.today().isoformat():
        flash("Walk date can't be in the future.", "error")
        return redirect(url_for(_redirect_target()))

    distance_km = None
    if raw_distance:
        try:
            distance_km = float(raw_distance)
        except ValueError:
            flash("Distance must be a number.", "error")
            return redirect(url_for(_redirect_target()))

    duration_min = None
    if raw_duration:
        try:
            duration_min = float(raw_duration)
        except ValueError:
            flash("Duration must be a number.", "error")
            return redirect(url_for(_redirect_target()))

    if db.checkin_walk(user_id, walk_date, distance_km, duration_min, note):
        flash(f"Logged a walk for {walk_date}.", "success")
    else:
        flash(f"You already have a walk logged for {walk_date}.", "error")

    return redirect(url_for(_redirect_target()))


@bp.route("/walking/<walk_date>/delete", methods=["POST"])
@auth.login_required
def delete(walk_date):
    current_user = auth.current_user()
    db.delete_walk(current_user["id"], walk_date)
    flash("Walk deleted.", "success")
    return redirect(url_for("walking.walking"))
