import csv
import io
import os
import re
from datetime import timedelta

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    Response,
    session,
    url_for,
)

from . import (
    auth,
    db,
    food_config,
    localtime,
    paths,
    progress as progress_module,
    progressive_load,
    quotes,
    workout_config,
)

bp = Blueprint("member", __name__)

METRIC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = auth.check_login(username, password)
        if user:
            session.clear()
            session["user_id"] = user["id"]
            flash("Logged in.", "success")
            return redirect(url_for("member.dashboard"))
        flash(
            "Invalid username or password, or your account isn't fully set up yet.",
            "error",
        )
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("public.index"))


PRIMARY_WEIGHT_METRIC = "weight_kg"
PRIMARY_HEIGHT_METRIC = "height_cm"


def _compute_bmi(latest):
    """Auto-calculate BMI from the latest logged weight + height, if both
    are available. Returns None otherwise so the template can show an
    empty state instead of a bogus number."""
    weight = next(
        (row["value"] for row in latest if row["metric_key"] == PRIMARY_WEIGHT_METRIC and row["value"] is not None),
        None,
    )
    height_cm = next(
        (row["value"] for row in latest if row["metric_key"] == PRIMARY_HEIGHT_METRIC and row["value"] is not None),
        None,
    )
    if not weight or not height_cm:
        return None

    bmi = weight / ((height_cm / 100) ** 2)
    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"
    return {"value": round(bmi, 1), "category": category}


@bp.route("/dashboard")
@auth.login_required
def dashboard():
    current_user = auth.current_user()
    user_id = current_user["id"]
    latest = db.latest_value_per_metric(user_id)
    config_exists = os.path.exists(paths.user_config_path(user_id))

    weight_def = next(
        (row for row in db.list_metric_defs(user_id) if row["metric_key"] == PRIMARY_WEIGHT_METRIC),
        None,
    )
    bmi = _compute_bmi(latest)

    today_iso = localtime.today().isoformat()
    recent_visits = db.list_recent_visits(user_id, limit=60)
    recent_walks = db.list_recent_walks(user_id, limit=60)
    checked_in_today = any(row["visit_date"] == today_iso for row in recent_visits)
    walked_today = any(row["walk_date"] == today_iso for row in recent_walks)
    progress_result = progress_module.compute_progress(user_id)

    weekly_activity = _compute_weekly_activity(recent_visits, recent_walks)
    health_score, health_label = _health_score(progress_result["status"])
    weight_goal = _compute_weight_goal(current_user, latest, user_id)
    distance_month_km, walks_this_month = _distance_this_month(recent_walks)
    weekly_goal_pct = _weekly_goal_pct(progress_result["attendance_signal"])
    health_insights = _compute_health_insights(latest)
    daily_quote = quotes.get_daily_quote()

    food_of_day = None
    if os.path.exists(paths.user_foods_path(user_id)):
        paths.ensure_user_files(user_id)
        food_cfg = food_config.load_config(paths.user_foods_path(user_id))
        food_of_day = _pick_food_of_day(food_cfg)

    plan_days = []
    today_index = None
    todays_workout = None
    if config_exists:
        paths.ensure_user_files(user_id)
        plan_config = workout_config.load_config(paths.user_config_path(user_id))
        plan_days = plan_config["days"]
        today_index = workout_config.pick_today_index(plan_days)
        progressive_load.annotate_days(plan_days, user_id, db)
        if today_index is not None:
            todays_workout = plan_days[today_index]

    return render_template(
        "member/dashboard.html",
        latest=latest,
        config_exists=config_exists,
        weight_metric=PRIMARY_WEIGHT_METRIC,
        weight_def=weight_def,
        bmi=bmi,
        today=today_iso,
        progress_result=progress_result,
        checked_in_today=checked_in_today,
        walked_today=walked_today,
        days=plan_days,
        today_index=today_index,
        todays_workout=todays_workout,
        weekly_activity=weekly_activity,
        health_score=health_score,
        health_label=health_label,
        weight_goal=weight_goal,
        distance_month_km=distance_month_km,
        walks_this_month=walks_this_month,
        weekly_goal_pct=weekly_goal_pct,
        health_insights=health_insights,
        daily_quote=daily_quote,
        food_of_day=food_of_day,
    )


# ---- dashboard "bento grid" widget helpers ---------------------------------

_HEALTH_SCORE_BY_STATUS = {
    "on_track": (88, "Great"),
    "mixed": (62, "Good"),
    "off_track": (35, "Needs Focus"),
    "insufficient_data": (50, "Getting Started"),
}


def _health_score(status):
    return _HEALTH_SCORE_BY_STATUS.get(status, (50, "Getting Started"))


def _weekly_goal_pct(attendance_signal):
    goal = attendance_signal.get("goal_weekly_visits") or 0
    visits = attendance_signal.get("visits_this_week") or 0
    if goal <= 0:
        return 0
    return min(100, round(visits / goal * 100))


def _compute_weekly_activity(recent_visits, recent_walks):
    """Builds the data for the dashboard's "Activity" bar chart: one bar per
    of the last 7 days (gym visit + walk both count), plus a %-change badge
    versus the 7 days before that - mirrors a typical fitness-app activity
    widget without needing any extra DB queries beyond what the dashboard
    already fetches for the check-in buttons."""
    visit_dates = {row["visit_date"] for row in recent_visits}
    walk_dates = {row["walk_date"] for row in recent_walks}

    def _score(iso_date):
        return (1 if iso_date in visit_dates else 0) + (1 if iso_date in walk_dates else 0)

    today = localtime.today()
    days = []
    for offset in range(6, -1, -1):
        d = today - timedelta(days=offset)
        days.append({"label": d.strftime("%a"), "score": _score(d.isoformat()), "is_today": offset == 0})

    max_score = max((d["score"] for d in days), default=0) or 1
    for d in days:
        d["height_pct"] = max(6, round(d["score"] / max_score * 100)) if d["score"] else 0

    this_week_total = sum(d["score"] for d in days)
    prev_week_total = sum(
        _score((today - timedelta(days=offset)).isoformat()) for offset in range(13, 6, -1)
    )
    if prev_week_total > 0:
        trend_pct = round((this_week_total - prev_week_total) / prev_week_total * 100)
    else:
        trend_pct = 100 if this_week_total > 0 else 0

    return {"days": days, "trend_pct": trend_pct, "this_week_total": this_week_total}


def _compute_weight_goal(user, latest, user_id):
    current_weight = next(
        (row["value"] for row in latest if row["metric_key"] == PRIMARY_WEIGHT_METRIC and row["value"] is not None),
        None,
    )
    entries_logged = len(db.metric_history(user_id, PRIMARY_WEIGHT_METRIC, limit=100000))
    return {
        "current_weight": current_weight,
        "goal_target_weight": user["goal_target_weight"],
        "entries_logged": entries_logged,
    }


def _compute_health_insights(latest):
    """Derives a few extra "for what it's worth" health indicators from
    whatever body metrics the user already has logged. Every indicator is
    independently optional - each only appears once its inputs exist - and
    these are general population guidelines, not medical advice, which the
    dashboard card says explicitly."""
    values = {
        row["metric_key"]: row["value"]
        for row in latest
        if row["value"] is not None
    }
    weight = values.get(PRIMARY_WEIGHT_METRIC)
    height_cm = values.get(PRIMARY_HEIGHT_METRIC)
    waist_cm = values.get("waist_cm")
    body_fat_pct = values.get("body_fat_pct")

    insights = []

    if height_cm:
        height_m = height_cm / 100
        low = round(18.5 * height_m * height_m, 1)
        high = round(24.9 * height_m * height_m, 1)
        insights.append({
            "label": "Healthy Weight Range",
            "value": f"{low}-{high} kg",
            "note": "based on a normal BMI (18.5-24.9) for your height",
        })

    if waist_cm and height_cm:
        ratio = round(waist_cm / height_cm, 2)
        if ratio < 0.5:
            category, tone = "Healthy", ""
        elif ratio < 0.6:
            category, tone = "Elevated Risk", "is-warning"
        else:
            category, tone = "High Risk", "is-danger"
        insights.append({
            "label": "Waist-to-Height Ratio",
            "value": str(ratio),
            "category": category,
            "tone": tone,
            "note": "keeping this under 0.5 is linked to lower cardiometabolic risk",
        })

    if body_fat_pct is not None:
        if body_fat_pct < 14:
            category, tone = "Athletic", ""
        elif body_fat_pct < 24:
            category, tone = "Fitness", ""
        elif body_fat_pct < 32:
            category, tone = "Average", "is-warning"
        else:
            category, tone = "Above Average", "is-danger"
        insights.append({
            "label": "Body Fat",
            "value": f"{body_fat_pct}%",
            "category": category,
            "tone": tone,
            "note": "rough unisex banding - trends over time matter more than the exact number",
        })

    if weight and height_cm and waist_cm is None and body_fat_pct is None:
        # Nudge people who've only ever logged weight/height toward the
        # metrics that unlock the rest of this card.
        insights.append({
            "label": "Unlock More Insights",
            "value": "Log your waist & body fat",
            "note": "adds waist-to-height ratio and a body-fat estimate here",
        })

    return insights


def _pick_food_of_day(food_cfg):
    """Deterministically rotates through every food in the user's own food
    guide, one per day (same idea as workout_config.pick_today_index) -
    no extra state, and it's stable all day so it doesn't shuffle on every
    dashboard reload. Returns None if the guide has no foods yet."""
    all_foods = [
        {"category": cat["name"], **food}
        for cat in food_cfg.get("categories", [])
        for food in cat.get("foods", [])
    ]
    if not all_foods:
        return None
    return all_foods[localtime.today().toordinal() % len(all_foods)]


def _distance_this_month(recent_walks):
    month_prefix = localtime.today().strftime("%Y-%m")
    total = 0.0
    count = 0
    for row in recent_walks:
        if row["walk_date"].startswith(month_prefix):
            count += 1
            if row["distance_km"] is not None:
                total += row["distance_km"]
    return round(total, 1), count


# ---- workout plan / config editor -----------------------------------------

@bp.route("/plan")
@auth.login_required
def plan():
    current_user = auth.current_user()
    user_id = current_user["id"]
    paths.ensure_user_files(user_id)
    config = workout_config.load_config(paths.user_config_path(user_id))
    today_index = workout_config.pick_today_index(config["days"])
    progressive_load.annotate_days(config["days"], user_id, db)
    return render_template(
        "member/plan.html",
        site=config["site"],
        days=config["days"],
        today_index=today_index,
        today=localtime.today().isoformat(),
    )


@bp.route("/plan/log-exercise", methods=["POST"])
@auth.login_required
def log_exercise():
    current_user = auth.current_user()
    user_id = current_user["id"]
    exercise_name = request.form.get("exercise_name", "").strip()
    raw_weight = request.form.get("weight_kg", "").strip()
    raw_reps = request.form.get("reps", "").strip()
    raw_sets = request.form.get("sets", "").strip()
    redirect_to = request.form.get("redirect_to", "plan")

    target = "member.dashboard" if redirect_to == "dashboard" else "member.plan"
    anchor = "#todays-workout" if redirect_to == "dashboard" else ""

    if not exercise_name:
        flash("Missing exercise name.", "error")
        return redirect(url_for(target) + anchor)

    weight_kg = None
    reps = None
    sets = None
    try:
        if raw_weight:
            weight_kg = float(raw_weight)
        if raw_reps:
            reps = int(raw_reps)
        if raw_sets:
            sets = int(raw_sets)
    except ValueError:
        flash("Weight must be a number and reps/sets must be whole numbers.", "error")
        return redirect(url_for(target) + anchor)

    db.log_exercise(
        user_id, localtime.today().isoformat(), exercise_name, weight_kg, reps, sets
    )
    flash(f"Logged {exercise_name}. Nice work!", "success")
    return redirect(url_for(target) + anchor)


@bp.route("/plan/edit", methods=["GET", "POST"])
@auth.login_required
def config_editor():
    current_user = auth.current_user()
    user_id = current_user["id"]
    config_path = paths.user_config_path(user_id)
    if request.method == "POST":
        raw_text = request.form.get("raw_yaml", "")
        try:
            workout_config.save_raw(
                config_path, raw_text, backup_dir=paths.user_backup_dir(user_id)
            )
            flash("Workout config saved. Your plan page now reflects your changes.", "success")
            return redirect(url_for("member.config_editor"))
        except workout_config.ConfigError as exc:
            flash(str(exc), "error")
            raw_text_to_show = raw_text
            return render_template("member/config_editor.html", raw_yaml=raw_text_to_show)

    raw_yaml = workout_config.load_raw(config_path)
    return render_template("member/config_editor.html", raw_yaml=raw_yaml)


@bp.route("/plan/backups")
@auth.login_required
def config_backups():
    current_user = auth.current_user()
    backup_dir = paths.user_backup_dir(current_user["id"])
    files = []
    if os.path.isdir(backup_dir):
        files = sorted(os.listdir(backup_dir), reverse=True)
    return render_template("member/config_backups.html", files=files)


@bp.route("/plan/backups/<path:filename>/restore", methods=["POST"])
@auth.login_required
def restore_backup(filename):
    current_user = auth.current_user()
    user_id = current_user["id"]
    backup_dir = paths.user_backup_dir(user_id)
    safe_name = os.path.basename(filename)
    backup_path = os.path.join(backup_dir, safe_name)
    if not os.path.isfile(backup_path):
        flash("Backup not found.", "error")
        return redirect(url_for("member.config_backups"))
    with open(backup_path, "r", encoding="utf-8") as fh:
        raw_text = fh.read()
    workout_config.save_raw(
        paths.user_config_path(user_id), raw_text, backup_dir=backup_dir
    )
    flash(f"Restored config from {safe_name}.", "success")
    return redirect(url_for("member.config_editor"))


@bp.route("/export/plan.yml")
@auth.login_required
def export_config():
    current_user = auth.current_user()
    raw_yaml = workout_config.load_raw(paths.user_config_path(current_user["id"]))
    return Response(
        raw_yaml,
        mimetype="text/yaml",
        headers={"Content-Disposition": "attachment; filename=gym.yml"},
    )


# ---- food guide / editor -----------------------------------------------------

@bp.route("/foods")
@auth.login_required
def food_guide():
    current_user = auth.current_user()
    user_id = current_user["id"]
    paths.ensure_user_files(user_id)
    config = food_config.load_config(paths.user_foods_path(user_id))
    return render_template(
        "member/foods.html", intro=config["intro"], categories=config["categories"]
    )


@bp.route("/foods/edit", methods=["GET", "POST"])
@auth.login_required
def foods_editor():
    current_user = auth.current_user()
    user_id = current_user["id"]
    foods_path = paths.user_foods_path(user_id)
    if request.method == "POST":
        raw_text = request.form.get("raw_yaml", "")
        try:
            food_config.save_raw(
                foods_path, raw_text, backup_dir=paths.user_backup_dir(user_id)
            )
            flash("Food guide saved. Your foods page now reflects your changes.", "success")
            return redirect(url_for("member.foods_editor"))
        except food_config.ConfigError as exc:
            flash(str(exc), "error")
            return render_template("member/food_editor.html", raw_yaml=raw_text)

    raw_yaml = food_config.load_raw(foods_path)
    return render_template("member/food_editor.html", raw_yaml=raw_yaml)


@bp.route("/foods/backups")
@auth.login_required
def food_backups():
    current_user = auth.current_user()
    backup_dir = paths.user_backup_dir(current_user["id"])
    files = []
    if os.path.isdir(backup_dir):
        files = sorted(
            (f for f in os.listdir(backup_dir) if f.startswith("foods-")), reverse=True
        )
    return render_template("member/food_backups.html", files=files)


@bp.route("/foods/backups/<path:filename>/restore", methods=["POST"])
@auth.login_required
def restore_food_backup(filename):
    current_user = auth.current_user()
    user_id = current_user["id"]
    backup_dir = paths.user_backup_dir(user_id)
    safe_name = os.path.basename(filename)
    backup_path = os.path.join(backup_dir, safe_name)
    if not os.path.isfile(backup_path):
        flash("Backup not found.", "error")
        return redirect(url_for("member.food_backups"))
    with open(backup_path, "r", encoding="utf-8") as fh:
        raw_text = fh.read()
    food_config.save_raw(
        paths.user_foods_path(user_id), raw_text, backup_dir=backup_dir
    )
    flash(f"Restored food guide from {safe_name}.", "success")
    return redirect(url_for("member.foods_editor"))


@bp.route("/export/foods.yml")
@auth.login_required
def export_foods():
    current_user = auth.current_user()
    raw_yaml = food_config.load_raw(paths.user_foods_path(current_user["id"]))
    return Response(
        raw_yaml,
        mimetype="text/yaml",
        headers={"Content-Disposition": "attachment; filename=foods.yml"},
    )


# ---- body metric tracker --------------------------------------------------

@bp.route("/tracker")
@auth.login_required
def tracker():
    current_user = auth.current_user()
    user_id = current_user["id"]
    metric_filter = request.args.get("metric") or None
    logs = db.list_logs(user_id, metric_key=metric_filter)
    defs = db.list_metric_defs(user_id)
    today = localtime.today().isoformat()
    return render_template(
        "member/tracker.html",
        logs=logs,
        defs=defs,
        metric_filter=metric_filter,
        today=today,
    )


@bp.route("/tracker/add", methods=["POST"])
@auth.login_required
def tracker_add():
    current_user = auth.current_user()
    user_id = current_user["id"]
    log_date = request.form.get("log_date") or localtime.today().isoformat()
    metric_key = request.form.get("metric_key", "")
    notes = request.form.get("notes", "").strip()
    raw_value = request.form.get("value", "").strip()
    return_to = "member.dashboard" if request.form.get("redirect_to") == "dashboard" else "member.tracker"

    try:
        value = float(raw_value)
    except ValueError:
        flash("Value must be a number.", "error")
        return redirect(url_for(return_to))

    known_keys = {row["metric_key"] for row in db.list_metric_defs(user_id)}
    if metric_key not in known_keys:
        flash("Unknown metric.", "error")
        return redirect(url_for(return_to))

    db.add_log(user_id, log_date, metric_key, value, notes)
    flash("Entry logged.", "success")
    return redirect(url_for(return_to))


@bp.route("/tracker/<int:log_id>/delete", methods=["POST"])
@auth.login_required
def tracker_delete(log_id):
    current_user = auth.current_user()
    db.delete_log(current_user["id"], log_id)
    flash("Entry deleted.", "success")
    return redirect(url_for("member.tracker"))


@bp.route("/tracker/history/<metric_key>")
@auth.login_required
def tracker_history_json(metric_key):
    current_user = auth.current_user()
    rows = db.metric_history(current_user["id"], metric_key, limit=200)
    return {
        "metric": metric_key,
        "points": [{"date": r["log_date"], "value": r["value"]} for r in rows],
    }


@bp.route("/export/logs.csv")
@auth.login_required
def export_logs_csv():
    current_user = auth.current_user()
    rows = db.list_logs(current_user["id"], limit=100000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "metric", "label", "unit", "value", "notes", "logged_at"])
    for r in rows:
        writer.writerow(
            [r["log_date"], r["metric_key"], r["label"], r["unit"], r["value"], r["notes"], r["created_at"]]
        )
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=body_logs.csv"},
    )


# ---- metric definitions ---------------------------------------------------

@bp.route("/metrics")
@auth.login_required
def metrics():
    current_user = auth.current_user()
    defs = db.list_metric_defs(current_user["id"])
    return render_template("member/metrics.html", defs=defs)


@bp.route("/metrics/add", methods=["POST"])
@auth.login_required
def metrics_add():
    current_user = auth.current_user()
    user_id = current_user["id"]
    metric_key = request.form.get("metric_key", "").strip().lower()
    label = request.form.get("label", "").strip()
    unit = request.form.get("unit", "").strip()
    try:
        sort_order = int(request.form.get("sort_order") or 0)
    except ValueError:
        sort_order = 0

    if not METRIC_KEY_RE.match(metric_key):
        flash(
            "Metric key must be lowercase letters/numbers/underscores, "
            "starting with a letter (e.g. 'neck_cm').",
            "error",
        )
        return redirect(url_for("member.metrics"))
    if not label:
        flash("Label is required.", "error")
        return redirect(url_for("member.metrics"))

    db.add_metric_def(user_id, metric_key, label, unit, sort_order)
    flash(f"Metric '{label}' saved.", "success")
    return redirect(url_for("member.metrics"))


@bp.route("/metrics/<metric_key>/delete", methods=["POST"])
@auth.login_required
def metrics_delete(metric_key):
    current_user = auth.current_user()
    db.delete_metric_def(current_user["id"], metric_key)
    flash("Metric and its logged history were deleted.", "success")
    return redirect(url_for("member.metrics"))


# ---- account ---------------------------------------------------------------

@bp.route("/account/password", methods=["GET", "POST"])
@auth.login_required
def change_password():
    current_user = auth.current_user()
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not auth.verify_password(current_user, current_password):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "error")
        else:
            db.set_user_password(current_user["id"], auth.hash_password(new_password))
            flash("Password updated.", "success")
            return redirect(url_for("member.dashboard"))
    return render_template("member/change_password.html", current_user=current_user)
