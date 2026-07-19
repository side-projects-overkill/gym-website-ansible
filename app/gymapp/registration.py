"""Self-service registration - Telegram verification is MANDATORY.

There is exactly one way to activate an account through this app: link it
to a Telegram chat via the bot, then set a password. There is no path that
creates a usable (`active`) account without that step.

The only Telegram endpoint this app ever talks to is the personal helper
service's small REST API (see `gymapp.telegram_bot` - never Telegram's Bot
API directly, no bot token, no webhook). That service already long-polls
Telegram for this bot, so `gymapp.telegram_poller` polls its `/updates`
endpoint in a background thread and hands each new update to
`handle_telegram_update()` below.

Flow:
    1. `/register` - user picks a username, we create a `pending_telegram`
       user row and hand them a Telegram deep link.
    2. User taps the link, Telegram opens a chat with our bot and sends a
       `/start <token>` message, which the poller picks up and routes to
       `handle_telegram_update()`. We link their chat_id to the user row
       (-> `pending_password`) and message them a fresh link to
       `/set-password/<token>`.
    3. `/set-password/<token>` - user sets a password (-> `active`), we
       seed their default metrics and config files. This is the ONLY route
       that can move a user to `active`, and it requires a token that only
       ever gets created after step 2 succeeds.

`/forgot-password` + `/reset-password/<token>` mirror step 3 for existing
accounts that lost their password, reusing the same Telegram delivery
channel (no email required) - and likewise only work for accounts that are
already linked to Telegram.
"""
import re

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from . import auth, db, paths, telegram_bot

bp = Blueprint("registration", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")

# Usernames in these statuses are already claimed and can't be re-registered.
_TAKEN_STATUSES = {"active", "pending_password"}


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()

        if not USERNAME_RE.match(username):
            flash(
                "Username must be 3-32 characters: letters, numbers, "
                "underscores, or hyphens only.",
                "error",
            )
            return render_template("register.html", username=username)

        existing = db.get_user_by_username(username)
        if existing and existing["status"] in _TAKEN_STATUSES:
            flash("Username already taken.", "error")
            return render_template("register.html", username=username)

        if existing and existing["status"] == "pending_telegram":
            # Abandoned registration (started but never linked Telegram).
            # Self-heal by reusing the existing pending row and issuing a
            # fresh link token, rather than deleting it: an old, unconsumed
            # link token still references this row via a foreign key, and
            # db.delete_pending_user_by_username() only deletes the `users`
            # row (not its tokens), which would violate that FK constraint.
            user_id = existing["id"]
        else:
            user_id = db.create_pending_user(username)

        helper_api_base = current_app.config.get("TELEGRAM_HELPER_API_BASE", "")
        bot_username = telegram_bot.get_bot_username(helper_api_base)
        token = db.create_link_token(user_id, purpose="link", ttl_minutes=30)
        return render_template(
            "register_link.html",
            deep_link=_telegram_deep_link(bot_username, token),
            bot_username=bot_username,
        )

    return render_template("register.html", username="")


def handle_telegram_update(update):
    """Process a single Telegram Update dict. Called by the background
    poller in `gymapp.telegram_poller` for every new update it sees."""
    message = update.get("message")
    if not message:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    chat_id = str(chat_id)
    telegram_username = chat.get("username")
    text = message.get("text", "") or ""

    if text.startswith("/start "):
        token = text[len("/start "):].strip()
        _handle_start_with_token(chat_id, telegram_username, token)
        return

    if text.startswith("/start"):
        _handle_start_without_token(chat_id)
        return


def _handle_start_with_token(chat_id, telegram_username, token):
    helper_api_base = current_app.config.get("TELEGRAM_HELPER_API_BASE", "")
    row = db.get_valid_link_token(token)
    if row is None or row["purpose"] != "link":
        telegram_bot.send_message(
            helper_api_base,
            chat_id,
            "That link has expired or was already used. Please register again "
            "or use /forgot-password on the site.",
        )
        return

    user_id = row["user_id"]
    db.set_user_telegram_chat_id(user_id, chat_id, telegram_username)
    db.consume_link_token(token)

    set_password_token = db.create_link_token(user_id, purpose="set_password", ttl_minutes=30)
    public_base_url = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    link = f"{public_base_url}/set-password/{set_password_token}"
    telegram_bot.send_message(
        helper_api_base,
        chat_id,
        f"You're verified! Tap this link to set your password:\n{link}",
    )


def _handle_start_without_token(chat_id):
    helper_api_base = current_app.config.get("TELEGRAM_HELPER_API_BASE", "")
    public_base_url = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
    existing_user = db.get_user_by_telegram_chat_id(chat_id)
    if existing_user:
        telegram_bot.send_message(
            helper_api_base,
            chat_id,
            f"Hi! Manage your account at {public_base_url}",
        )


@bp.route("/set-password/<token>", methods=["GET", "POST"])
def set_password(token):
    return _password_form(token, purpose="set_password", template="set_password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    return _password_form(token, purpose="reset", template="reset_password.html")


def _password_form(token, purpose, template):
    row = db.get_valid_link_token(token)
    if row is None or row["purpose"] != purpose:
        return render_template("invalid_link.html")

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template(template, token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template(template, token=token)

        user_id = row["user_id"]
        db.set_user_password(user_id, auth.hash_password(password))
        db.consume_link_token(token)

        if purpose == "set_password":
            db.seed_default_metrics(user_id)
            paths.ensure_user_files(user_id)

        flash("Password set! You can now log in.", "success")
        return redirect(url_for("member.login"))

    return render_template(template, token=token)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        user = db.get_user_by_username(username)
        if user and user["telegram_chat_id"]:
            token = db.create_link_token(user["id"], purpose="reset", ttl_minutes=30)
            public_base_url = current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
            link = f"{public_base_url}/reset-password/{token}"
            telegram_bot.send_message(
                current_app.config.get("TELEGRAM_HELPER_API_BASE", ""),
                user["telegram_chat_id"],
                f"Password reset requested. Tap this link to set a new password:\n{link}",
            )

        flash(
            "If that account exists and is linked to Telegram, we've sent a reset link there.",
            "success",
        )
        return redirect(url_for("registration.forgot_password"))

    return render_template("forgot_password.html")


def _telegram_deep_link(bot_username, token):
    if not bot_username:
        return ""
    return f"https://t.me/{bot_username}?start={token}"
