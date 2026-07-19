import csv
import io
import os
import re
from datetime import date

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

from . import auth, db, food_config, paths, progress as progress_module, workout_config

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

    today_iso = date.today().isoformat()
    checked_in_today = any(
        row["visit_date"] == today_iso for row in db.list_recent_visits(user_id, limit=1)
    )
    progress_result = progress_module.compute_progress(user_id)

    return render_template(
        "member/dashboard.html",
        latest=latest,
        config_exists=config_exists,
        weight_metric=PRIMARY_WEIGHT_METRIC,
        weight_def=weight_def,
        today=today_iso,
        progress_result=progress_result,
        checked_in_today=checked_in_today,
    )


# ---- workout plan / config editor -----------------------------------------

@bp.route("/plan")
@auth.login_required
def plan():
    current_user = auth.current_user()
    user_id = current_user["id"]
    paths.ensure_user_files(user_id)
    config = workout_config.load_config(paths.user_config_path(user_id))
    return render_template("member/plan.html", site=config["site"], days=config["days"])


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
    today = date.today().isoformat()
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
    log_date = request.form.get("log_date") or date.today().isoformat()
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
