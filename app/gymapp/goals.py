"""Goal-setting routes (goal type, target weight, weekly visit target).

Self-contained blueprint - not yet registered in `__init__.py`. Blueprint
name "goals", no url_prefix.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from . import auth, db

bp = Blueprint("goals", __name__)

ALLOWED_GOAL_TYPES = {"lose", "gain", "maintain"}
WEIGHT_METRIC_KEY = "weight_kg"


@bp.route("/goals", methods=["GET", "POST"])
@auth.login_required
def goals():
    current_user = auth.current_user()
    user_id = current_user["id"]

    if request.method == "POST":
        goal_type = request.form.get("goal_type", "").strip()
        raw_target_weight = request.form.get("goal_target_weight", "").strip()
        raw_weekly_visits = request.form.get("goal_weekly_visits", "").strip()

        error = None
        goal_target_weight = None
        goal_weekly_visits = None

        if goal_type not in ALLOWED_GOAL_TYPES:
            error = "Please choose a valid goal type."

        if not error:
            try:
                goal_weekly_visits = int(raw_weekly_visits)
                if goal_weekly_visits <= 0:
                    raise ValueError
            except ValueError:
                error = "Weekly visit goal must be a positive whole number."

        if not error and raw_target_weight:
            try:
                goal_target_weight = float(raw_target_weight)
                if goal_target_weight <= 0:
                    raise ValueError
            except ValueError:
                error = "Target weight must be a positive number."

        if error:
            flash(error, "error")
            return redirect(url_for("goals.goals"))

        db.update_user_goals(user_id, goal_type, goal_target_weight, goal_weekly_visits)
        flash("Goals updated.", "success")
        return redirect(url_for("goals.goals"))

    user = db.get_user(user_id)
    latest = db.latest_value_per_metric(user_id)
    current_weight = next(
        (row for row in latest if row["metric_key"] == WEIGHT_METRIC_KEY and row["value"] is not None),
        None,
    )

    return render_template(
        "member/goals.html",
        user=user,
        current_weight=current_weight,
        allowed_goal_types=sorted(ALLOWED_GOAL_TYPES),
    )
