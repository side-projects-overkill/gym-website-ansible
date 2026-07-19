#!/usr/bin/env python3
"""Operator CLI for the Gym Tracker app.

Used both for local development and by the Ansible deploy playbook:

    # One-time migration of a pre-multi-user install (auth.json + a single
    # gym.yml/foods.yml) into the new per-user schema. Idempotent.
    python3 manage.py --data-dir /opt/gymapp/data migrate

    # Escape hatch to create/recover an account without going through
    # Telegram registration.
    python3 manage.py --data-dir /opt/gymapp/data create-user \\
        --username someone --password 'secret'
"""
import argparse
import json
import os
import shutil
import sys

from gymapp import create_app, db, paths
from gymapp.auth import hash_password

MIGRATION_MARKER = ".migration_v1_done"


def cmd_migrate(args):
    app = create_app(data_dir=args.data_dir)
    data_dir = app.config["DATA_DIR"]
    marker_path = os.path.join(data_dir, MIGRATION_MARKER)
    if os.path.exists(marker_path):
        print("Already migrated.")
        return 0

    with app.app_context():
        auth_json_path = os.path.join(data_dir, "auth.json")
        if os.path.exists(auth_json_path):
            with open(auth_json_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            username = payload["username"]
            password_hash = payload["password_hash"]

            # Resuming after a partially-failed previous attempt (e.g. this
            # process died mid-migration): reuse the already-created user
            # instead of failing on a duplicate-username constraint.
            existing = db.get_user_by_username(username)
            user_id = existing["id"] if existing else db.create_migrated_user(username, password_hash)
            paths.user_dir(user_id)

            old_config = os.path.join(data_dir, "gym.yml")
            if os.path.exists(old_config):
                shutil.move(old_config, paths.user_config_path(user_id))

            old_foods = os.path.join(data_dir, "foods.yml")
            if os.path.exists(old_foods):
                shutil.move(old_foods, paths.user_foods_path(user_id))

            old_backups = os.path.join(data_dir, "backups")
            if os.path.isdir(old_backups) and os.listdir(old_backups):
                new_backups = paths.user_backup_dir(user_id)
                for name in os.listdir(old_backups):
                    shutil.move(
                        os.path.join(old_backups, name),
                        os.path.join(new_backups, name),
                    )

            db.backfill_user_id(user_id)

            os.rename(auth_json_path, auth_json_path + ".migrated")

            print(f"Migrated user '{username}' -> user_id={user_id}")
        else:
            print("No auth.json found; nothing to migrate (fresh install).")

    with open(marker_path, "w", encoding="utf-8") as fh:
        fh.write("done\n")

    return 0


def cmd_create_user(args):
    app = create_app(data_dir=args.data_dir)
    with app.app_context():
        if db.get_user_by_username(args.username):
            print(f"Username '{args.username}' already exists.", file=sys.stderr)
            return 1
        user_id = db.create_migrated_user(args.username, hash_password(args.password))
        print(f"Created user '{args.username}' -> user_id={user_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Gym Tracker operator CLI")
    parser.add_argument("--data-dir", default=None, help="Override data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_migrate = sub.add_parser(
        "migrate", help="One-time migration to the multi-user schema (idempotent)"
    )
    p_migrate.set_defaults(func=cmd_migrate)

    p_create = sub.add_parser(
        "create-user", help="Create an active account directly (bypasses Telegram)"
    )
    p_create.add_argument("--username", required=True)
    p_create.add_argument("--password", required=True)
    p_create.set_defaults(func=cmd_create_user)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
