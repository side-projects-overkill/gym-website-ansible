"""Daily motivational quote for the dashboard.

Tries a free, keyless quotes API first (ZenQuotes' "today" endpoint, which
returns the same quote to everyone all day - handy since it means the
result is cacheable). Falls back to a small local list, picked
deterministically by date, if the API is unreachable or slow - this must
never make the dashboard fail to load just because of a flaky third party.

Cached in-process per calendar day so we only ever make at most one outbound
request per day per app worker, regardless of how many times the dashboard
is loaded.
"""
import logging

import requests

from . import localtime

logger = logging.getLogger(__name__)

QUOTE_API_URL = "https://zenquotes.io/api/today"
REQUEST_TIMEOUT_SECONDS = 4

# Used whenever the API can't be reached (offline, rate-limited, etc.) - a
# small, hand-picked set of quotes with a fitness/consistency bent so they
# fit the app even in fallback mode.
FALLBACK_QUOTES = [
    {"text": "The only bad workout is the one that didn't happen.", "author": "Unknown"},
    {"text": "Success is the sum of small efforts, repeated day in and day out.", "author": "Robert Collier"},
    {"text": "It's not about having time, it's about making time.", "author": "Unknown"},
    {"text": "Discipline is choosing between what you want now and what you want most.", "author": "Abraham Lincoln"},
    {"text": "The pain of discipline weighs ounces; the pain of regret weighs tons.", "author": "Jim Rohn"},
    {"text": "You don't have to be extreme, just consistent.", "author": "Unknown"},
    {"text": "Take care of your body. It's the only place you have to live.", "author": "Jim Rohn"},
    {"text": "A one-hour workout is 4% of your day. No excuses.", "author": "Unknown"},
    {"text": "The body achieves what the mind believes.", "author": "Unknown"},
    {"text": "Motivation gets you started. Habit keeps you going.", "author": "Jim Ryun"},
    {"text": "Every workout counts. Every meal counts. Every step counts.", "author": "Unknown"},
    {"text": "Progress, not perfection.", "author": "Unknown"},
    {"text": "Small daily improvements are the key to staggering long-term results.", "author": "Unknown"},
    {"text": "You are one workout away from a good mood.", "author": "Unknown"},
    {"text": "Strength does not come from winning. Your struggles develop your strengths.", "author": "Arnold Schwarzenegger"},
]

_cache = {"date": None, "quote": None}


def _fetch_from_api():
    try:
        response = requests.get(QUOTE_API_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
        if not payload:
            return None
        entry = payload[0]
        text = (entry.get("q") or "").strip()
        author = (entry.get("a") or "").strip()
        if not text:
            return None
        return {"text": text, "author": author or "Unknown"}
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        logger.info("Quote API unavailable, using local fallback: %s", exc)
        return None


def _fallback_quote(today):
    return FALLBACK_QUOTES[today.toordinal() % len(FALLBACK_QUOTES)]


def get_daily_quote(today=None):
    """Returns {"text": ..., "author": ...} for today, from cache/API/
    fallback in that order of preference."""
    today = today or localtime.today()
    today_key = today.isoformat()

    if _cache["date"] == today_key and _cache["quote"] is not None:
        return _cache["quote"]

    quote = _fetch_from_api() or _fallback_quote(today)
    _cache["date"] = today_key
    _cache["quote"] = quote
    return quote
