"""SQLite storage layer.

Everything the app persists (users, gym visits, body-metric logs, metric
definitions) lives under a single data directory so the whole app state
can be backed up or moved by copying that one directory.

Multi-user note: every row that belongs to a member is scoped by
`user_id`. Callers are responsible for always supplying the current
user's id - this module does not do any authorization itself.
"""
import secrets
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT,
    telegram_chat_id TEXT UNIQUE,
    telegram_username TEXT,
    status TEXT NOT NULL DEFAULT 'pending_telegram',
    goal_type TEXT NOT NULL DEFAULT 'maintain',
    goal_target_weight REAL,
    goal_weekly_visits INTEGER NOT NULL DEFAULT 3,
    goal_weekly_walks INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_link_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    purpose TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS gym_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    visit_date TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (user_id, visit_date)
);

CREATE TABLE IF NOT EXISTS walks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    walk_date TEXT NOT NULL,
    distance_km REAL,
    duration_min REAL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE (user_id, walk_date)
);

CREATE TABLE IF NOT EXISTS metric_defs (
    metric_key  TEXT NOT NULL,
    label       TEXT NOT NULL,
    unit        TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    user_id     INTEGER REFERENCES users(id),
    PRIMARY KEY (user_id, metric_key)
);

-- No FK on metric_key: it is no longer unique on its own (the PK above is
-- now (user_id, metric_key)), and a single-column FK against it wouldn't be
-- valid. The application layer validates metric_key against the current
-- user's own metric_defs rows before every insert.
CREATE TABLE IF NOT EXISTS body_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date    TEXT NOT NULL,
    metric_key  TEXT NOT NULL,
    value       REAL NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);

-- Progressive-overload tracking: one row per logged set (or top set) of an
-- exercise. `exercise_name` is a free-text match against the YAML workout
-- config's exercise names rather than an FK, since the config can be
-- edited/reordered/renamed freely and isn't itself in the database.
CREATE TABLE IF NOT EXISTS exercise_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    log_date      TEXT NOT NULL,
    exercise_name TEXT NOT NULL,
    weight_kg     REAL,
    reps          INTEGER,
    sets          INTEGER,
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_body_logs_date ON body_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_body_logs_metric ON body_logs(metric_key);
CREATE INDEX IF NOT EXISTS idx_gym_visits_user_date ON gym_visits(user_id, visit_date);
CREATE INDEX IF NOT EXISTS idx_walks_user_date ON walks(user_id, walk_date);
CREATE INDEX IF NOT EXISTS idx_exercise_logs_lookup ON exercise_logs(user_id, exercise_name, log_date);

-- Generic small key/value store for app-internal bookkeeping (e.g. the
-- Telegram poller's last-seen update_id high-water mark).
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

DEFAULT_METRICS = [
    # metric_key,     label,        unit,   sort_order
    ("weight_kg", "Weight", "kg", 1),
    ("height_cm", "Height", "cm", 2),
    ("body_fat_pct", "Body Fat", "%", 3),
    ("waist_cm", "Waist", "cm", 4),
    ("chest_cm", "Chest", "cm", 5),
    ("arm_cm", "Arm", "cm", 6),
    ("hip_cm", "Hips", "cm", 7),
    ("thigh_cm", "Thighs", "cm", 8),
]

# Metrics that used to be in DEFAULT_METRICS above and were retired -
# _migrate_metric_catalog() below removes them (and their logged history,
# mirroring what the "delete metric" button in the UI already does) for
# every existing user, not just future registrations.
RETIRED_DEFAULT_METRIC_KEYS = ("resting_hr",)


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = _connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _add_column_if_missing(conn, table, column, column_def):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")


def _migrate_metric_defs_composite_pk(conn):
    """Upgrade a pre-existing `metric_defs` table to the composite
    `PRIMARY KEY (user_id, metric_key)` schema, preserving all rows.

    SQLite can't ALTER a table's primary key in place, so this does the
    standard create-new-table / copy-rows / drop-old / rename dance. Safe to
    call on:
      - a fresh DB with no `metric_defs` table yet (no-op; the `CREATE TABLE
        IF NOT EXISTS` in SCHEMA creates it with the correct schema)
      - an already-migrated table with the composite PK (no-op)
      - an old single-column-PK table, with or without a `user_id` column
        already ALTER'd onto it by a previous version of this function
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'metric_defs'"
    ).fetchone()
    if exists is None:
        return

    table_info = conn.execute("PRAGMA table_info(metric_defs)").fetchall()
    pk_columns = {row[1] for row in table_info if row[5] > 0}  # row[5] = pk position, 0 = not in PK
    if pk_columns == {"user_id", "metric_key"}:
        return  # already on the composite-PK schema

    has_user_id = "user_id" in {row[1] for row in table_info}

    conn.execute(
        """
        CREATE TABLE metric_defs_new (
            metric_key  TEXT NOT NULL,
            label       TEXT NOT NULL,
            unit        TEXT NOT NULL DEFAULT '',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            user_id     INTEGER REFERENCES users(id),
            PRIMARY KEY (user_id, metric_key)
        )
        """
    )
    user_id_select = "user_id" if has_user_id else "NULL"
    conn.execute(
        f"INSERT INTO metric_defs_new (metric_key, label, unit, sort_order, user_id) "
        f"SELECT metric_key, label, unit, sort_order, {user_id_select} FROM metric_defs"
    )
    conn.execute("DROP TABLE metric_defs")
    conn.execute("ALTER TABLE metric_defs_new RENAME TO metric_defs")


def _migrate_body_logs_drop_fk(conn):
    """Recreate a pre-existing `body_logs` table without its old single-column
    FK to `metric_defs(metric_key)`, if present.

    That FK predates the multi-user refactor. Once `metric_defs`'s primary
    key became composite `(user_id, metric_key)`, `metric_key` alone is no
    longer unique, so the old FK definition is invalid - SQLite then raises
    `foreign key mismatch` on *any* write to `metric_defs` (the referenced
    table) while `PRAGMA foreign_keys = ON`, even though `body_logs` itself
    isn't being touched. Safe to call on:
      - a fresh DB with no `body_logs` table yet (no-op)
      - a table that already has no FKs (no-op)
      - an old table with the stale FK, with or without a `user_id` column
        already ALTER'd onto it
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'body_logs'"
    ).fetchone()
    if exists is None:
        return

    fks = conn.execute("PRAGMA foreign_key_list(body_logs)").fetchall()
    if not fks:
        return  # already on the FK-less schema

    table_info = conn.execute("PRAGMA table_info(body_logs)").fetchall()
    has_user_id = "user_id" in {row[1] for row in table_info}

    conn.execute(
        """
        CREATE TABLE body_logs_new (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date    TEXT NOT NULL,
            metric_key  TEXT NOT NULL,
            value       REAL NOT NULL,
            notes       TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            user_id     INTEGER REFERENCES users(id)
        )
        """
    )
    user_id_select = "user_id" if has_user_id else "NULL"
    conn.execute(
        "INSERT INTO body_logs_new (id, log_date, metric_key, value, notes, created_at, user_id) "
        f"SELECT id, log_date, metric_key, value, notes, created_at, {user_id_select} FROM body_logs"
    )
    conn.execute("DROP TABLE body_logs")
    conn.execute("ALTER TABLE body_logs_new RENAME TO body_logs")


def _migrate_metric_catalog(conn):
    """Retroactively apply DEFAULT_METRICS additions/removals to every
    existing user, not just future registrations - `seed_default_metrics`
    only ever runs once, at account activation. Safe to call every
    startup: the INSERTs are idempotent (OR IGNORE against the composite
    PK) and the DELETEs are no-ops once the retired rows are gone."""
    users_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    if users_exists is None:
        return

    user_ids = [row[0] for row in conn.execute("SELECT id FROM users")]
    new_keys = {"hip_cm", "thigh_cm"}
    for user_id in user_ids:
        for key, label, unit, sort_order in DEFAULT_METRICS:
            if key not in new_keys:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO metric_defs (metric_key, label, unit, sort_order, user_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, label, unit, sort_order, user_id),
            )

    for key in RETIRED_DEFAULT_METRIC_KEYS:
        conn.execute("DELETE FROM body_logs WHERE metric_key = ?", (key,))
        conn.execute("DELETE FROM metric_defs WHERE metric_key = ?", (key,))


def init_db(db_path):
    """Create tables and run lightweight migrations. Safe to call every startup."""
    conn = _connect(db_path)
    try:
        # Foreign key enforcement must be off for the table-swap dance below
        # (SQLite disallows dropping a table that's an active FK target, or
        # inserting into one, while enforcement is on).
        conn.execute("PRAGMA foreign_keys = OFF")
        _migrate_metric_defs_composite_pk(conn)
        _migrate_body_logs_drop_fk(conn)
        conn.executescript(SCHEMA)
        _add_column_if_missing(
            conn, "body_logs", "user_id", "user_id INTEGER REFERENCES users(id)"
        )
        _add_column_if_missing(
            conn, "users", "goal_weekly_walks", "goal_weekly_walks INTEGER NOT NULL DEFAULT 3"
        )
        _migrate_metric_catalog(conn)
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---- generic app state (key/value) ----------------------------------------

def get_state(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row is not None else default


def set_state(key, value):
    db = get_db()
    db.execute(
        "INSERT INTO app_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    db.commit()


# ---- users -----------------------------------------------------------------

def create_pending_user(username):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (username, status, created_at) VALUES (?, 'pending_telegram', ?)",
        (username, now_iso()),
    )
    db.commit()
    return cur.lastrowid


def create_migrated_user(username, password_hash):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (username, password_hash, status, created_at) "
        "VALUES (?, ?, 'active', ?)",
        (username, password_hash, now_iso()),
    )
    db.commit()
    return cur.lastrowid


def get_user(user_id):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def get_user_by_username(username):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_telegram_chat_id(chat_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM users WHERE telegram_chat_id = ?", (chat_id,)
    ).fetchone()


def set_user_telegram_chat_id(user_id, chat_id, telegram_username=None):
    db = get_db()
    db.execute(
        "UPDATE users SET telegram_chat_id = ?, telegram_username = ?, "
        "status = CASE WHEN status = 'pending_telegram' THEN 'pending_password' ELSE status END "
        "WHERE id = ?",
        (chat_id, telegram_username, user_id),
    )
    db.commit()


def set_user_password(user_id, password_hash):
    db = get_db()
    db.execute(
        "UPDATE users SET password_hash = ?, status = 'active' WHERE id = ?",
        (password_hash, user_id),
    )
    db.commit()


def update_user_goals(user_id, goal_type, goal_target_weight, goal_weekly_visits, goal_weekly_walks):
    db = get_db()
    db.execute(
        "UPDATE users SET goal_type = ?, goal_target_weight = ?, goal_weekly_visits = ?, "
        "goal_weekly_walks = ? WHERE id = ?",
        (goal_type, goal_target_weight, goal_weekly_visits, goal_weekly_walks, user_id),
    )
    db.commit()


def delete_pending_user_by_username(username):
    db = get_db()
    row = db.execute(
        "SELECT id FROM users WHERE username = ? AND status = 'pending_telegram'",
        (username,),
    ).fetchone()
    if row is None:
        return
    user_id = row["id"]
    # Clean up child rows first so the FK constraint on telegram_link_tokens
    # (enforced via PRAGMA foreign_keys = ON) doesn't reject the delete.
    db.execute("DELETE FROM telegram_link_tokens WHERE user_id = ?", (user_id,))
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()


def backfill_user_id(user_id):
    """Assign every legacy (pre-multi-user) metric_defs/body_logs row that
    has no owner yet to `user_id`. Used by the one-time migration."""
    db = get_db()
    db.execute("UPDATE metric_defs SET user_id = ? WHERE user_id IS NULL", (user_id,))
    db.execute("UPDATE body_logs SET user_id = ? WHERE user_id IS NULL", (user_id,))
    db.commit()


# ---- telegram link tokens ---------------------------------------------------

def create_link_token(user_id, purpose, ttl_minutes=30):
    db = get_db()
    token = secrets.token_urlsafe(24)
    created = datetime.now(timezone.utc)
    expires = created.timestamp() + ttl_minutes * 60
    expires_at = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(timespec="seconds")
    db.execute(
        "INSERT INTO telegram_link_tokens (token, user_id, purpose, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (token, user_id, purpose, now_iso(), expires_at),
    )
    db.commit()
    return token


def get_valid_link_token(token):
    db = get_db()
    row = db.execute(
        "SELECT * FROM telegram_link_tokens WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        return None
    if row["consumed_at"] is not None:
        return None
    if row["expires_at"] <= now_iso():
        return None
    return row


def consume_link_token(token):
    db = get_db()
    db.execute(
        "UPDATE telegram_link_tokens SET consumed_at = ? WHERE token = ?",
        (now_iso(), token),
    )
    db.commit()


# ---- gym visits --------------------------------------------------------------

def checkin_visit(user_id, visit_date, note=""):
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO gym_visits (user_id, visit_date, note, created_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id, visit_date, note, now_iso()),
    )
    db.commit()
    return cur.rowcount > 0


def delete_visit(user_id, visit_date):
    db = get_db()
    db.execute(
        "DELETE FROM gym_visits WHERE user_id = ? AND visit_date = ?",
        (user_id, visit_date),
    )
    db.commit()


def list_recent_visits(user_id, limit=60):
    db = get_db()
    return db.execute(
        "SELECT * FROM gym_visits WHERE user_id = ? ORDER BY visit_date DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def count_visits_since(user_id, since_date):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM gym_visits WHERE user_id = ? AND visit_date >= ?",
        (user_id, since_date),
    ).fetchone()
    return row["n"]


def total_visit_count(user_id):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM gym_visits WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["n"]


# ---- walking tracker (mirrors gym visits above) -----------------------------

def checkin_walk(user_id, walk_date, distance_km=None, duration_min=None, note=""):
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO walks (user_id, walk_date, distance_km, duration_min, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, walk_date, distance_km, duration_min, note, now_iso()),
    )
    db.commit()
    return cur.rowcount > 0


def delete_walk(user_id, walk_date):
    db = get_db()
    db.execute(
        "DELETE FROM walks WHERE user_id = ? AND walk_date = ?",
        (user_id, walk_date),
    )
    db.commit()


def list_recent_walks(user_id, limit=60):
    db = get_db()
    return db.execute(
        "SELECT * FROM walks WHERE user_id = ? ORDER BY walk_date DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def count_walks_since(user_id, since_date):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM walks WHERE user_id = ? AND walk_date >= ?",
        (user_id, since_date),
    ).fetchone()
    return row["n"]


def total_walk_count(user_id):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM walks WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["n"]


# ---- progressive-overload exercise logs -----------------------------------

def log_exercise(user_id, log_date, exercise_name, weight_kg=None, reps=None, sets=None, note=""):
    db = get_db()
    db.execute(
        "INSERT INTO exercise_logs (user_id, log_date, exercise_name, weight_kg, reps, sets, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, log_date, exercise_name, weight_kg, reps, sets, note, now_iso()),
    )
    db.commit()


def latest_exercise_log(user_id, exercise_name):
    db = get_db()
    return db.execute(
        "SELECT * FROM exercise_logs WHERE user_id = ? AND exercise_name = ? "
        "ORDER BY log_date DESC, id DESC LIMIT 1",
        (user_id, exercise_name),
    ).fetchone()


def latest_exercise_logs_by_name(user_id):
    """One row per exercise name: whichever log is most recent for that
    exercise. Used to annotate a whole workout day's exercises in a single
    query instead of one round-trip per exercise."""
    db = get_db()
    rows = db.execute(
        """
        SELECT el.* FROM exercise_logs el
        WHERE el.user_id = ? AND el.id = (
            SELECT id FROM exercise_logs
            WHERE user_id = el.user_id AND exercise_name = el.exercise_name
            ORDER BY log_date DESC, id DESC LIMIT 1
        )
        """,
        (user_id,),
    ).fetchall()
    return {row["exercise_name"]: row for row in rows}


def list_exercise_history(user_id, exercise_name, limit=20):
    db = get_db()
    return db.execute(
        "SELECT * FROM exercise_logs WHERE user_id = ? AND exercise_name = ? "
        "ORDER BY log_date DESC, id DESC LIMIT ?",
        (user_id, exercise_name, limit),
    ).fetchall()


# ---- metric definitions -------------------------------------------------

def list_metric_defs(user_id):
    db = get_db()
    return db.execute(
        "SELECT * FROM metric_defs WHERE user_id = ? ORDER BY sort_order, label",
        (user_id,),
    ).fetchall()


def add_metric_def(user_id, metric_key, label, unit, sort_order=0):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO metric_defs (metric_key, label, unit, sort_order, user_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (metric_key, label, unit, sort_order, user_id),
    )
    db.commit()


def delete_metric_def(user_id, metric_key):
    db = get_db()
    db.execute(
        "DELETE FROM body_logs WHERE metric_key = ? AND user_id = ?", (metric_key, user_id)
    )
    db.execute(
        "DELETE FROM metric_defs WHERE metric_key = ? AND user_id = ?", (metric_key, user_id)
    )
    db.commit()


def seed_default_metrics(user_id):
    """Insert the DEFAULT_METRICS rows for a brand new user, skipping any
    that already exist for them."""
    db = get_db()
    existing = {
        row[0]
        for row in db.execute(
            "SELECT metric_key FROM metric_defs WHERE user_id = ?", (user_id,)
        )
    }
    for key, label, unit, order in DEFAULT_METRICS:
        if key not in existing:
            db.execute(
                "INSERT INTO metric_defs (metric_key, label, unit, sort_order, user_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, label, unit, order, user_id),
            )
    db.commit()


# ---- body logs -----------------------------------------------------------

def add_log(user_id, log_date, metric_key, value, notes=""):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO body_logs (log_date, metric_key, value, notes, created_at, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (log_date, metric_key, value, notes, now_iso(), user_id),
    )
    db.commit()
    return cursor.lastrowid


def delete_log(user_id, log_id):
    db = get_db()
    db.execute("DELETE FROM body_logs WHERE id = ? AND user_id = ?", (log_id, user_id))
    db.commit()


def list_logs(user_id, metric_key=None, limit=500):
    db = get_db()
    if metric_key:
        rows = db.execute(
            "SELECT l.*, m.label, m.unit FROM body_logs l "
            "JOIN metric_defs m ON m.metric_key = l.metric_key AND m.user_id = l.user_id "
            "WHERE l.metric_key = ? AND l.user_id = ? "
            "ORDER BY l.log_date DESC, l.id DESC LIMIT ?",
            (metric_key, user_id, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT l.*, m.label, m.unit FROM body_logs l "
            "JOIN metric_defs m ON m.metric_key = l.metric_key AND m.user_id = l.user_id "
            "WHERE l.user_id = ? "
            "ORDER BY l.log_date DESC, l.id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return rows


def metric_history(user_id, metric_key, limit=100):
    db = get_db()
    rows = db.execute(
        "SELECT log_date, value FROM body_logs WHERE metric_key = ? AND user_id = ? "
        "ORDER BY log_date ASC, id ASC LIMIT ?",
        (metric_key, user_id, limit),
    ).fetchall()
    return rows


def latest_value_per_metric(user_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT m.metric_key, m.label, m.unit, l.value, l.log_date
        FROM metric_defs m
        LEFT JOIN body_logs l ON l.metric_key = m.metric_key AND l.user_id = m.user_id
        AND l.id = (
            SELECT id FROM body_logs
            WHERE metric_key = m.metric_key AND user_id = m.user_id
            ORDER BY log_date DESC, id DESC LIMIT 1
        )
        WHERE m.user_id = ?
        ORDER BY m.sort_order, m.label
        """,
        (user_id,),
    ).fetchall()
    return rows


# ---- date lookups used by the health-data importer ------------------------

def visit_dates(user_id):
    rows = get_db().execute("SELECT visit_date FROM gym_visits WHERE user_id = ?", (user_id,)).fetchall()
    return [r["visit_date"] for r in rows]


def walk_dates(user_id):
    rows = get_db().execute("SELECT walk_date FROM walks WHERE user_id = ?", (user_id,)).fetchall()
    return [r["walk_date"] for r in rows]


def log_dates(user_id, metric_key):
    rows = get_db().execute(
        "SELECT DISTINCT log_date FROM body_logs WHERE user_id = ? AND metric_key = ?",
        (user_id, metric_key),
    ).fetchall()
    return [r["log_date"] for r in rows]
