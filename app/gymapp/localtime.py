"""App-wide "what day is it" helper.

`date.today()` uses the server's system clock/timezone, which won't
necessarily match the people actually using the app. This server runs on
UTC, but everything that means "today" here - which workout day opens by
default, the weekly activity chart, streaks, check-in dates, the daily
quote/food rotation - should follow the user's own local calendar day, not
the host's. Around midnight-5:30am local time, "today" on a UTC server is
still "yesterday", so anything using `date.today()` directly is silently
off by a day for part of every day.

This is deliberately a single configured timezone (not per-request/
per-browser detection) since this app is used by one household, not
across timezones - see APP_TIMEZONE in create_app().
"""
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"

_zone_cache = {}


def _zone(tz_name):
    if tz_name not in _zone_cache:
        _zone_cache[tz_name] = ZoneInfo(tz_name)
    return _zone_cache[tz_name]


def _configured_tz_name():
    try:
        from flask import current_app

        return current_app.config.get("APP_TIMEZONE", DEFAULT_TIMEZONE)
    except RuntimeError:
        # Called outside a Flask app/request context (e.g. a one-off
        # script) - fall back rather than crashing.
        return DEFAULT_TIMEZONE


def now():
    """Current datetime in the app's configured local timezone."""
    return datetime.now(_zone(_configured_tz_name()))


def today():
    """Current date in the app's configured local timezone - use this
    everywhere the code previously used `date.today()`."""
    return now().date()
