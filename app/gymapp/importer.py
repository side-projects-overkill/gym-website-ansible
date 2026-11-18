"""Upload -> preview -> confirm flow for watch/phone health exports.

The upload is parsed immediately and only the small summary is kept, as a
single-use JSON file under the user's own data dir (imports/<token>.json),
until you confirm or it expires. Tokens are random and checked against a
strict pattern, and lookups are scoped to the logged-in user's folder, so a
pending import can't be read or applied by anyone else.
"""
import os
import secrets
import time
from datetime import timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from . import auth, db, health_import, localtime, paths

bp = Blueprint("importer", __name__)

PENDING_TTL_SECONDS = 24 * 3600


def _pending_dir(user_id):
    d = os.path.join(paths.user_dir(user_id), "imports")
    os.makedirs(d, exist_ok=True)
    return d


def _pending_path(user_id, token):
    if not health_import.TOKEN_RE.match(token or ""):
        abort(404)
    path = os.path.join(_pending_dir(user_id), f"{token}.json")
    if not os.path.isfile(path):
        abort(404)
    return path


def _cleanup_expired(user_id):
    d = _pending_dir(user_id)
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if name.endswith(".json") and time.time() - os.path.getmtime(p) > PENDING_TTL_SECONDS:
            os.remove(p)


def last_import_key(user_id):
    return f"last_import:{user_id}"


@bp.route("/import", methods=["GET", "POST"])
@auth.login_required
def upload():
    user = auth.current_user()
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Choose a file to import.", "error")
            return redirect(url_for("importer.upload"))
        weight_unit = "lb" if request.form.get("weight_unit") == "lb" else "kg"
        try:
            result = health_import.parse_upload(f.stream, f.filename, weight_unit=weight_unit)
        except health_import.ImportError_ as exc:
            flash(str(exc), "error")
            return redirect(url_for("importer.upload"))
        if result.is_empty():
            flash("No walks, strength workouts or weight found in that file.", "error")
            return redirect(url_for("importer.upload"))
        _cleanup_expired(user["id"])
        token = secrets.token_urlsafe(24)
        with open(os.path.join(_pending_dir(user["id"]), f"{token}.json"), "w") as fh:
            fh.write(result.to_json())
        return redirect(url_for("importer.preview", token=token))

    return render_template("member/import.html", last_import=db.get_state(last_import_key(user["id"])))


def _ranged(result, choice, last_import):
    today = localtime.today()
    if choice == "30":
        return result.since((today - timedelta(days=30)).isoformat())
    if choice == "90":
        return result.since((today - timedelta(days=90)).isoformat())
    if choice == "new" and last_import:
        return result.since(last_import[:10])
    return result


@bp.route("/import/<token>", methods=["GET", "POST"])
@auth.login_required
def preview(token):
    user = auth.current_user()
    path = _pending_path(user["id"], token)
    with open(path) as fh:
        result = health_import.ImportResult.from_json(fh.read())
    last_import = db.get_state(last_import_key(user["id"]))

    if request.method == "POST":
        chosen = _ranged(result, request.form.get("range", "all"), last_import)
        added = health_import.apply(user["id"], chosen)
        os.remove(path)
        db.set_state(last_import_key(user["id"]), localtime.today().isoformat())
        flash(f"Synced from {result.source}: {added['walks']} walks, {added['gym']} gym sessions, "
              f"{added['weights']} weights added.", "success")
        return redirect(url_for("member.dashboard"))

    ranges = {key: health_import.preview_counts(user["id"], _ranged(result, key, last_import))
              for key in ("new", "30", "90", "all")}
    first, last = result.date_range()
    return render_template(
        "member/import_preview.html",
        token=token, result=result, ranges=ranges, last_import=last_import,
        first=first, last=last,
        found={"walks": len(result.walks), "gym": len(result.gym), "weights": len(result.weights)},
    )
