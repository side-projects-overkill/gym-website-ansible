"""Regression tests for workout plan editor, exercise logging, goals."""


def test_plan_page_seeds_default_config(logged_in, user):
    r = logged_in.get("/plan")
    assert r.status_code == 200


def test_config_editor_roundtrip(logged_in, user):
    raw = (
        "site:\n"
        "  name: Test Gym\n"
        "days:\n"
        "  - name: Push\n"
        "    exercises:\n"
        "      - name: Bench Press\n"
        "        sets_reps: 3 x 8-12\n"
    )
    r = logged_in.post("/plan/edit", data={"raw_yaml": raw})
    assert r.status_code == 302

    from gymapp import paths, workout_config
    cfg = workout_config.load_config(paths.user_config_path(user["id"]))
    assert cfg["site"]["name"] == "Test Gym"
    assert cfg["days"][0]["exercises"][0]["name"] == "Bench Press"


def test_config_editor_rejects_invalid_yaml(logged_in, user):
    r = logged_in.post("/plan/edit", data={"raw_yaml": "days: [unclosed"})
    assert r.status_code == 200  # re-renders editor with error
    assert b"saved" not in r.data.lower() or b"error" in r.data.lower()


def test_config_backup_created_on_save(logged_in, user):
    raw = "site:\n  name: A\ndays: []\n"
    logged_in.post("/plan/edit", data={"raw_yaml": raw})
    logged_in.post("/plan/edit", data={"raw_yaml": raw.replace("A", "B")})
    from gymapp import paths
    backups = [f for f in __import__("os").listdir(paths.user_backup_dir(user["id"]))]
    assert any(f.startswith("gym-") for f in backups)


def test_export_plan_yml(logged_in, user):
    logged_in.get("/plan")  # seed
    r = logged_in.get("/export/plan.yml")
    assert r.status_code == 200
    assert "yaml" in r.headers["Content-Type"] or "text" in r.headers["Content-Type"]


def test_log_exercise(logged_in, user):
    from gymapp import db

    r = logged_in.post(
        "/plan/log-exercise",
        data={"exercise_name": "Bench Press", "weight_kg": "60", "reps": "10", "sets": "3"},
    )
    assert r.status_code == 302
    log = db.latest_exercise_log(user["id"], "Bench Press")
    assert log["weight_kg"] == 60.0
    assert log["reps"] == 10


def test_log_exercise_ajax_with_suggestion(logged_in, user):
    r = logged_in.post(
        "/plan/log-exercise",
        data={
            "exercise_name": "Squat",
            "weight_kg": "100",
            "reps": "12",
            "sets": "3",
            "sets_reps": "3 x 8-12",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    payload = r.get_json()
    assert payload["ok"] is True
    # 12 reps >= target 12 -> suggest adding weight
    assert payload["suggestion"] is not None
    assert "102.5" in payload["suggestion"]


def test_log_exercise_rejects_bad_numbers(logged_in, user):
    r = logged_in.post(
        "/plan/log-exercise",
        data={"exercise_name": "Row", "weight_kg": "abc", "reps": "10"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_log_exercise_rejects_missing_name(logged_in, user):
    r = logged_in.post(
        "/plan/log-exercise",
        data={"exercise_name": "", "weight_kg": "10"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 400


def test_progressive_load_suggest_repeat():
    from gymapp.progressive_load import suggest_next

    log = {"weight_kg": 60.0, "reps": 8}
    assert suggest_next(log, 12) == "Repeat 60kg, aim for more reps"


def test_progressive_load_suggest_add_weight():
    from gymapp.progressive_load import suggest_next

    log = {"weight_kg": 60.0, "reps": 12}
    assert suggest_next(log, 12) == "Add weight -> try 62.5kg"


def test_progressive_load_no_weight():
    from gymapp.progressive_load import suggest_next

    assert suggest_next({"weight_kg": None, "reps": 5}, 10) is None
    assert suggest_next(None, 10) is None


def test_parse_target_reps():
    from gymapp.progressive_load import parse_target_reps

    assert parse_target_reps("3 x 8-12") == 12
    assert parse_target_reps("4x10") == 10
    assert parse_target_reps("") is None


# ---- goals ------------------------------------------------------------------


def test_goals_page(logged_in):
    r = logged_in.get("/goals")
    assert r.status_code == 200


def test_goals_update(logged_in, user):
    from gymapp import db

    r = logged_in.post(
        "/goals",
        data={
            "goal_type": "lose",
            "goal_target_weight": "75",
            "goal_weekly_visits": "4",
            "goal_weekly_walks": "5",
        },
    )
    assert r.status_code == 302
    fresh = db.get_user(user["id"])
    assert fresh["goal_type"] == "lose"
    assert fresh["goal_target_weight"] == 75.0
    assert fresh["goal_weekly_visits"] == 4
    assert fresh["goal_weekly_walks"] == 5


def test_goals_rejects_bad_type(logged_in, user):
    from gymapp import db

    logged_in.post(
        "/goals",
        data={
            "goal_type": "shrink",
            "goal_weekly_visits": "4",
            "goal_weekly_walks": "5",
        },
    )
    assert db.get_user(user["id"])["goal_type"] == "maintain"


def test_goals_rejects_zero_visits(logged_in, user):
    logged_in.post(
        "/goals",
        data={"goal_type": "lose", "goal_weekly_visits": "0", "goal_weekly_walks": "5"},
    )
    from gymapp import db
    assert db.get_user(user["id"])["goal_weekly_visits"] == 3  # unchanged default
