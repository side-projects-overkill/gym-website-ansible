"""Gym check-in / attendance tracking routes.

Self-contained blueprint - not yet registered in `__init__.py`. See the
module docstring in the task description this was built against for the
integration contract (blueprint name "attendance", no url_prefix).
"""
from datetime import date, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from . import auth, db, localtime

bp = Blueprint("attendance", __name__)


def _redirect_target():
    """Mirror member.py's `redirect_to` hidden-field pattern where present,
    falling back to the attendance page itself."""
    if request.form.get("redirect_to") == "dashboard":
        # The integrator may wire a check-in widget on the dashboard that
        # wants to land back there; member.dashboard is registered by the
        # integration pass, so this only works once that's wired up.
        return "member.dashboard"
    return "attendance.attendance"


def _wants_json():
    """See member._wants_json - the quick check-in button submits via
    background fetch() so the page never reloads."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


@bp.route("/attendance")
@auth.login_required
def attendance():
    current_user = auth.current_user()
    user_id = current_user["id"]
    today_date = localtime.today()
    today = today_date.isoformat()

    recent_visits = db.list_recent_visits(user_id, limit=60)
    checked_in_today = any(row["visit_date"] == today for row in recent_visits)

    since_7d = (today_date - timedelta(days=6)).isoformat()
    since_30d = (today_date - timedelta(days=29)).isoformat()

    stats = {
        "total": db.total_visit_count(user_id),
        "last_7_days": db.count_visits_since(user_id, since_7d),
        "last_30_days": db.count_visits_since(user_id, since_30d),
    }

    return render_template(
        "member/attendance.html",
        recent_visits=recent_visits,
        checked_in_today=checked_in_today,
        stats=stats,
        today=today,
    )


@bp.route("/attendance/checkin", methods=["POST"])
@auth.login_required
def checkin():
    current_user = auth.current_user()
    user_id = current_user["id"]
    today = localtime.today().isoformat()

    checked_in = db.checkin_visit(user_id, today)
    message = "Checked in for today. Nice work!" if checked_in else "Already checked in today."

    if _wants_json():
        return jsonify({"ok": checked_in, "message": message})

    flash(message, "success" if checked_in else "error")
    return redirect(url_for(_redirect_target()))


@bp.route("/attendance/add", methods=["POST"])
@auth.login_required
def add():
    current_user = auth.current_user()
    user_id = current_user["id"]
    visit_date = request.form.get("visit_date", "").strip()
    note = request.form.get("note", "").strip()

    try:
        date.fromisoformat(visit_date)
    except ValueError:
        flash("Please provide a valid date.", "error")
        return redirect(url_for(_redirect_target()))

    if visit_date > localtime.today().isoformat():
        flash("Visit date can't be in the future.", "error")
        return redirect(url_for(_redirect_target()))

    if db.checkin_visit(user_id, visit_date, note):
        flash(f"Logged a visit for {visit_date}.", "success")
    else:
        flash(f"You already have a visit logged for {visit_date}.", "error")

    return redirect(url_for(_redirect_target()))


@bp.route("/attendance/<visit_date>/delete", methods=["POST"])
@auth.login_required
def delete(visit_date):
    current_user = auth.current_user()
    db.delete_visit(current_user["id"], visit_date)
    flash("Visit deleted.", "success")
    return redirect(url_for("attendance.attendance"))
