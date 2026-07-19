"""Thin wrapper around a personal Telegram helper API.

This app does NOT talk to Telegram's Bot API directly and does NOT hold a
bot token. The bot (@hybridx_gym_tracker_bot) is already operated via a
separate personal helper service that long-polls Telegram (`getUpdates`)
for message delivery. A bot can only use one delivery mode at a time -
webhook or long-polling - so registering our own webhook would silently
break that other service. Instead we act as a client of its small REST
API (see http://<helper host>/docs for the live schema):

    GET  {base}/send      -> not used
    POST {base}/send      body: {"chat_id": "...", "text": "..."}
    GET  {base}/updates   -> {"success": true, "updates": [<Telegram Update>, ...]}
    GET  {base}/bot/info  -> basic bot metadata, used as a connectivity check

Kept dependency-free of the rest of the app (no Flask imports) so it can
be exercised standalone/from tests.
"""
import logging
import time

import requests

logger = logging.getLogger(__name__)

# Simple in-memory cache for the bot's @username (rarely changes, and every
# /register page load would otherwise cost a round trip to the helper).
_bot_username_cache = {"value": None, "fetched_at": 0}
_BOT_USERNAME_CACHE_TTL_SECONDS = 300


def send_message(helper_api_base, chat_id, text):
    """Send a Telegram message via the helper API. Returns True on success.

    Never raises - network issues, a misconfigured/unreachable helper, etc.
    are logged and swallowed so an outage can never crash the caller.
    """
    if not helper_api_base:
        print(f"[telegram_bot] no helper API configured, would have sent to {chat_id}: {text}")
        return False

    url = f"{helper_api_base.rstrip('/')}/send"
    try:
        response = requests.post(
            url,
            json={"chat_id": str(chat_id), "text": text},
            timeout=10,
        )
        if response.status_code != 200:
            logger.warning(
                "[telegram_bot] send failed (%s): %s", response.status_code, response.text
            )
            return False
        return True
    except requests.RequestException as exc:
        logger.warning("[telegram_bot] send raised %s", exc)
        return False


def get_bot_username(helper_api_base):
    """Return the bot's @username (without the leading @), fetched from the
    helper API and cached briefly. Returns "" on any error or if unconfigured
    - callers should handle that gracefully (e.g. by hiding the deep link)."""
    if not helper_api_base:
        return ""

    now = time.monotonic()
    if _bot_username_cache["value"] and now - _bot_username_cache["fetched_at"] < _BOT_USERNAME_CACHE_TTL_SECONDS:
        return _bot_username_cache["value"]

    url = f"{helper_api_base.rstrip('/')}/bot/info"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        username = (payload.get("bot") or {}).get("username", "")
        if username:
            _bot_username_cache["value"] = username
            _bot_username_cache["fetched_at"] = now
        return username
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[telegram_bot] get_bot_username raised %s", exc)
        return _bot_username_cache["value"] or ""


def fetch_updates(helper_api_base, timeout=10):
    """Fetch recent updates from the helper API.

    Returns a list of Telegram Update dicts (possibly empty). Never raises -
    returns [] on any error so a poller loop can just keep going.
    """
    if not helper_api_base:
        return []

    url = f"{helper_api_base.rstrip('/')}/updates"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get("updates", []) or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[telegram_bot] fetch_updates raised %s", exc)
        return []
