"""Load/save the YAML file that drives the public workout page."""
from datetime import date

import yaml

from . import yaml_store
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
    return date.today().weekday() % len(days)
