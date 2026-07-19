"""Generic helper for editable, validated, backed-up YAML config files.

Both the workout program and the food guide are "just a YAML file the
admin edits in a textarea" - this module holds the shared load/validate/
save/backup mechanics so each config type only has to define its own
schema validation.
"""
import os
import shutil
import time

import yaml

MAX_BACKUPS = 20


class ConfigError(ValueError):
    pass


def load_raw(path):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def parse_yaml(raw_text, on_error=None):
    """Parse YAML text, returning `on_error` (default {}) if it's invalid or
    empty. Used for read paths that must never crash a page render."""
    if not raw_text or not raw_text.strip():
        return {} if on_error is None else on_error
    try:
        return yaml.safe_load(raw_text) or {}
    except yaml.YAMLError:
        return {} if on_error is None else on_error


def save_raw(path, raw_text, backup_dir, validate_fn, backup_prefix="backup"):
    """Validate `raw_text` with `validate_fn` (raises ConfigError on bad
    input), then atomically write it to `path`, keeping a timestamped
    backup of whatever was there before."""
    validate_fn(raw_text)

    if backup_dir and os.path.exists(path):
        os.makedirs(backup_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, os.path.join(backup_dir, f"{backup_prefix}-{stamp}.yml"))
        _prune_backups(backup_dir, backup_prefix)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        fh.write(raw_text)
    os.replace(tmp_path, path)


def _prune_backups(backup_dir, backup_prefix):
    files = sorted(
        (
            os.path.join(backup_dir, f)
            for f in os.listdir(backup_dir)
            if f.startswith(backup_prefix) and f.endswith(".yml")
        ),
        key=os.path.getmtime,
        reverse=True,
    )
    for stale in files[MAX_BACKUPS:]:
        os.remove(stale)
