"""Background thread that polls the personal Telegram helper API for new
messages, since this bot's delivery mode is long-polling (owned by that
separate helper service) rather than a webhook to us - see
`gymapp.telegram_bot` for why.

Started once per app process from `create_app()`, gated behind the
`ENABLE_TELEGRAM_POLLER` config flag so tests and local dev don't spin up a
thread that makes real network calls unless explicitly opted in.
"""
import logging
import threading
import time

from . import db, telegram_bot

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
LAST_UPDATE_ID_KEY = "telegram_poller_last_update_id"

_started = False
_lock = threading.Lock()


def start_background_poller(app):
    """Idempotently start the poller thread for this app process."""
    global _started
    with _lock:
        if _started:
            return
        _started = True

    thread = threading.Thread(
        target=_poll_loop, args=(app,), name="telegram-poller", daemon=True
    )
    thread.start()
    logger.info("[telegram_poller] started background polling thread")


def _poll_loop(app):
    from . import registration  # deferred: avoid a circular import at module load time

    while True:
        try:
            with app.app_context():
                _poll_once(app, registration)
        except Exception:
            logger.exception("[telegram_poller] error during poll cycle")
        time.sleep(POLL_INTERVAL_SECONDS)


def _poll_once(app, registration):
    helper_api_base = app.config.get("TELEGRAM_HELPER_API_BASE", "")
    if not helper_api_base:
        return

    last_seen = int(db.get_state(LAST_UPDATE_ID_KEY, "0") or "0")
    updates = telegram_bot.fetch_updates(helper_api_base)

    new_max = last_seen
    for update in sorted(updates, key=lambda u: u.get("update_id", 0)):
        update_id = update.get("update_id", 0)
        if update_id <= last_seen:
            continue
        try:
            registration.handle_telegram_update(update)
        except Exception:
            logger.exception(
                "[telegram_poller] error handling update_id=%s", update_id
            )
        new_max = max(new_max, update_id)

    if new_max != last_seen:
        db.set_state(LAST_UPDATE_ID_KEY, str(new_max))
