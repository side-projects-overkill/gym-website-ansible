import os
import shutil

from flask import Flask

from . import db as db_module

APP_ROOT = os.path.dirname(os.path.dirname(__file__))
SEED_DIR = os.path.join(APP_ROOT, "config")


def create_app(data_dir=None):
    app = Flask(__name__)

    data_dir = data_dir or os.environ.get("GYMAPP_DATA_DIR") or os.path.join(
        APP_ROOT, "data"
    )
    os.makedirs(data_dir, exist_ok=True)

    app.config.update(
        DATA_DIR=data_dir,
        DB_PATH=os.path.join(data_dir, "gym.db"),
        SECRET_KEY=_load_secret_key(data_dir),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # The ONLY Telegram-related endpoint this app talks to: a personal
        # helper service that already long-polls Telegram for this bot
        # (e.g. "http://192.168.1.23:5000/api"). No bot token, no webhook,
        # no other Telegram integration anywhere in this app - see
        # gymapp/telegram_bot.py and gymapp/telegram_poller.py.
        TELEGRAM_HELPER_API_BASE=os.environ.get("GYMAPP_TELEGRAM_HELPER_API_BASE", ""),
        PUBLIC_BASE_URL=os.environ.get(
            "GYMAPP_PUBLIC_BASE_URL", "http://127.0.0.1:5000"
        ),
        # Off by default so tests/local dev never spin up a thread that
        # makes real network calls; the systemd unit turns this on.
        ENABLE_TELEGRAM_POLLER=os.environ.get("GYMAPP_ENABLE_TELEGRAM_POLLER", "") == "1",
    )

    db_module.init_db(app.config["DB_PATH"])
    app.teardown_appcontext(db_module.close_db)

    from . import attendance, goals, member, public, registration, walking

    app.register_blueprint(public.bp)
    app.register_blueprint(member.bp)
    app.register_blueprint(registration.bp)
    app.register_blueprint(attendance.bp)
    app.register_blueprint(goals.bp)
    app.register_blueprint(walking.bp)

    # Cache-busting query string for static assets, derived from the newest
    # mtime under static/ (deterministic across all gunicorn workers, unlike
    # a random per-process token). This app is fronted by an external CDN/
    # cache we don't control (see templates using `asset_version`), which
    # otherwise happily keeps serving a stale style.css/chart.js for hours
    # after a deploy since it doesn't respect the origin's Cache-Control.
    app.config["ASSET_VERSION"] = _compute_asset_version(app.static_folder)

    @app.context_processor
    def _inject_asset_version():
        return {"asset_version": app.config["ASSET_VERSION"]}

    if app.config["ENABLE_TELEGRAM_POLLER"] and app.config["TELEGRAM_HELPER_API_BASE"]:
        from . import telegram_poller

        telegram_poller.start_background_poller(app)

    return app


def _seed_if_missing(dest_path, seed_path):
    if not os.path.exists(dest_path) and os.path.exists(seed_path):
        shutil.copy2(seed_path, dest_path)


def _compute_asset_version(static_folder):
    try:
        newest = max(
            os.path.getmtime(os.path.join(static_folder, name))
            for name in os.listdir(static_folder)
        )
        return str(int(newest))
    except (OSError, ValueError):
        return "0"


def _load_secret_key(data_dir):
    from . import auth

    return auth.get_or_create_secret_key(data_dir)
