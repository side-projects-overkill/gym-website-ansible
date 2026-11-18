"""Load/save the YAML file that drives the public workout page."""
import re

import yaml

from . import localtime, yaml_store
from .yaml_store import ConfigError, load_raw  # re-exported for callers

BACKUP_PREFIX = "gym"


def load_config(config_path):
    """Parse the YAML file into the dict used by templates.

    Returns a safe empty structure if the file is missing or invalid so the
    public page never hard-crashes because of a bad edit.
    """
    data = yaml_store.parse_yaml(load_raw(config_path))
    data.setdefault("site", {})
    data["site"].setdefault("title", "Gym Tracker")
    data["site"].setdefault("subtitle", "")
    data["site"].setdefault("rules", [])
    data.setdefault("days", [])
    return data


def validate(raw_text):
    """Parse & sanity-check YAML text. Raises ConfigError with a human
    readable message on failure. Returns the parsed dict on success."""
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc

    if data is None:
        raise ConfigError("Config cannot be empty.")
    if not isinstance(data, dict):
        raise ConfigError("Top-level YAML must be a mapping (site/days).")
    site = data.get("site") or {}
    if not isinstance(site, dict):
        raise ConfigError("'site' must be a mapping.")
    rules = site.get("rules", [])
    if not isinstance(rules, list) or not all(isinstance(r, str) for r in rules):
        raise ConfigError("'site.rules' must be a list of text lines.")
    if "days" in data and not isinstance(data["days"], list):
        raise ConfigError("'days' must be a list.")
    for day in data.get("days", []):
        if not isinstance(day, dict) or "name" not in day:
            raise ConfigError("Every day needs at least a 'name' field.")
        exercises = day.get("exercises", [])
        if not isinstance(exercises, list):
            raise ConfigError(f"'exercises' under '{day.get('name')}' must be a list.")
        for ex in exercises:
            if not isinstance(ex, dict) or "name" not in ex:
                raise ConfigError(
                    f"Every exercise under '{day.get('name')}' needs a 'name' field."
                )
    return data


def save_raw(config_path, raw_text, backup_dir=None):
    yaml_store.save_raw(config_path, raw_text, backup_dir, validate, BACKUP_PREFIX)


def pick_today_index(days):
    """Best-effort guess at "today's" day in the program: cycles through
    the configured days in order by calendar weekday (Monday -> index 0,
    Tuesday -> index 1, ...), wrapping around for splits shorter than a
    week. There's no explicit weekday mapping in the YAML, so this is a
    simple deterministic default rather than a scheduling feature.

    Returns None if there are no configured days.
    """
    if not days:
        return None
    return localtime.today().weekday() % len(days)


_REST_MINSEC = re.compile(r"^\s*(\d+):(\d{1,2})\s*$")
_REST_NUM_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds?|m|min|mins|minutes?)?\b", re.I)


def parse_rest_seconds(rest):
    """Turn a free-text rest like "90s", "2 min", "60-90s" or "1:30" into
    seconds for the auto rest timer. Ranges use the upper bound. Returns
    None when there's no number to work with ("as needed", "")."""
    if not rest or not isinstance(rest, str):
        return None
    m = _REST_MINSEC.match(rest)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    matches = _REST_NUM_UNIT.findall(rest)
    if not matches:
        return None
    unit = next((u for _, u in reversed(matches) if u), "s").lower()
    value = float(matches[-1][0])
    seconds = value * 60 if unit.startswith("m") else value
    return int(round(seconds)) or None
