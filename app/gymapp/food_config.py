"""Load/save the YAML file behind the high-volume food guide.

"High-volume" / low energy-density foods let you eat a filling amount of
food for relatively few calories, which is the whole point of this page:
help with weight loss without going hungry.
"""
import yaml

from . import yaml_store
from .yaml_store import ConfigError, load_raw  # re-exported for callers

BACKUP_PREFIX = "foods"

DEFAULT_INTRO = (
    "High-volume, low-calorie-density foods let you eat a satisfying amount "
    "of food while keeping calories in check. Within each category, foods "
    "are sorted by calories per 100g - lower is better for volume eating."
)


def load_config(config_path):
    """Parse the YAML file into the dict used by templates: categories with
    their foods sorted by calorie density (lowest first)."""
    data = yaml_store.parse_yaml(load_raw(config_path))
    intro = data.get("intro") or DEFAULT_INTRO
    categories = data.get("categories") or []

    normalized = []
    for cat in categories:
        if not isinstance(cat, dict):
            continue
        foods = cat.get("foods") or []
        foods = sorted(foods, key=lambda f: f.get("calories_per_100g", 0))
        normalized.append({"name": cat.get("name", "Other"), "foods": foods})

    return {"intro": intro, "categories": normalized}


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
        raise ConfigError("Top-level YAML must be a mapping (intro/categories).")
    if "categories" in data and not isinstance(data["categories"], list):
        raise ConfigError("'categories' must be a list.")
    for cat in data.get("categories", []):
        if not isinstance(cat, dict) or "name" not in cat:
            raise ConfigError("Every category needs a 'name' field.")
        foods = cat.get("foods", [])
        if not isinstance(foods, list):
            raise ConfigError(f"'foods' under '{cat.get('name')}' must be a list.")
        for food in foods:
            if not isinstance(food, dict) or "name" not in food:
                raise ConfigError(
                    f"Every food under '{cat.get('name')}' needs a 'name' field."
                )
            if "calories_per_100g" not in food:
                raise ConfigError(
                    f"'{food.get('name')}' needs a 'calories_per_100g' field."
                )
            try:
                float(food["calories_per_100g"])
            except (TypeError, ValueError):
                raise ConfigError(
                    f"'{food.get('name')}' calories_per_100g must be a number."
                )
    return data


def save_raw(config_path, raw_text, backup_dir=None):
    yaml_store.save_raw(config_path, raw_text, backup_dir, validate, BACKUP_PREFIX)
