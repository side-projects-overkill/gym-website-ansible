"""Regression tests for dashboard rendering + food guide + manage.py CLI."""
import subprocess
import sys


def test_dashboard_renders(logged_in):
    r = logged_in.get("/dashboard")
    assert r.status_code == 200


def test_dashboard_bmi_computation(app):
    from gymapp.member import _compute_bmi

    latest = [
        {"metric_key": "weight_kg", "value": 80.0},
        {"metric_key": "height_cm", "value": 180.0},
    ]
    bmi = _compute_bmi(latest)
    assert bmi["value"] == 24.7
    assert bmi["category"] == "Normal"


def test_dashboard_bmi_missing_height():
    from gymapp.member import _compute_bmi

    latest = [{"metric_key": "weight_kg", "value": 80.0}]
    assert _compute_bmi(latest) is None


def test_foods_page_seeds(logged_in):
    r = logged_in.get("/foods")
    assert r.status_code == 200


def test_foods_editor_roundtrip(logged_in, user):
    raw = "intro: hi\ncategories: []\n"
    r = logged_in.post("/foods/edit", data={"raw_yaml": raw})
    assert r.status_code == 302
    from gymapp import paths
    import os
    assert os.path.exists(paths.user_foods_path(user["id"]))


def test_export_foods_yml(logged_in, user):
    logged_in.get("/foods")  # seed
    r = logged_in.get("/export/foods.yml")
    assert r.status_code == 200


def test_manage_create_user(app, tmp_path):
    env = {
        k: v
        for k, v in __import__("os").environ.items()
        if not k.startswith("GYMAPP")
    }
    result = subprocess.run(
        [
            sys.executable,
            "manage.py",
            "--data-dir",
            str(tmp_path / "mdata"),
            "create-user",
            "--username",
            "cliuser",
            "--password",
            "password123",
        ],
        cwd=__import__("os").path.dirname(__import__("os").path.dirname(
            __import__("os").path.abspath(__file__)
        )),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "cliuser" in result.stdout

    # The created user can actually log in.
    from gymapp import create_app, db
    app2 = create_app(data_dir=str(tmp_path / "mdata"))
    with app2.app_context():
        assert db.get_user_by_username("cliuser") is not None


def test_manage_migrate_fresh_is_noop(tmp_path):
    import os
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "manage.py", "--data-dir", str(tmp_path / "m"),
         "migrate"],
        cwd=app_dir, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "fresh install" in result.stdout
