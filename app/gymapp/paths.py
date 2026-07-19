"""Per-user file paths.

Every member gets their own workout plan / food guide YAML (plus config
backups) under `<DATA_DIR>/users/<user_id>/`, instead of the old single
global config shared by everyone.
"""
import os

from flask import current_app


def user_dir(user_id):
    path = os.path.join(current_app.config["DATA_DIR"], "users", str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def user_config_path(user_id):
    return os.path.join(user_dir(user_id), "gym.yml")


def user_foods_path(user_id):
    return os.path.join(user_dir(user_id), "foods.yml")


def user_backup_dir(user_id):
    path = os.path.join(user_dir(user_id), "backups")
    os.makedirs(path, exist_ok=True)
    return path


def ensure_user_files(user_id):
    from . import SEED_DIR, _seed_if_missing

    _seed_if_missing(user_config_path(user_id), os.path.join(SEED_DIR, "gym.yml"))
    _seed_if_missing(user_foods_path(user_id), os.path.join(SEED_DIR, "foods.yml"))
