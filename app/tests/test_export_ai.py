"""Feature A - AI-readable progress export (TDD: written RED first).

Covers: JSON schema validity, Markdown structure + system-prompt wrapper,
date-range filtering, empty-state handling, routes + auth guards.
"""
import json

from gymapp import db, localtime


def _d(days_ago):
    from datetime import timedelta
    from gymapp import localtime
    return (localtime.today() - timedelta(days=days_ago)).isoformat()


def _seed_rich_history(user):
    """A few exercise sessions, body logs, visits and walks on recent dates."""
    db.log_exercise(user["id"], _d(14), "Bench Press", 60.0, 10, 3)
    db.log_exercise(user["id"], _d(7), "Bench Press", 62.5, 10, 3)
    db.log_exercise(user["id"], _d(0), "Bench Press", 62.5, 8, 3)
    db.log_exercise(user["id"], _d(0), "Squat", 100.0, 12, 3)
    db.add_log(user["id"], _d(14), "weight_kg", 80.0)
    db.add_log(user["id"], _d(0), "weight_kg", 79.0)
    db.checkin_visit(user["id"], _d(12))
    db.checkin_visit(user["id"], _d(5))
    db.checkin_walk(user["id"], _d(10), 5.0, 50.0)


# ---- module-level unit tests -----------------------------------------------


def test_build_export_schema(app, user):
    from gymapp.export_ai import build_export

    _seed_rich_history(user)
    payload = build_export(user["id"], db, days=90)

    assert payload["format_version"] == 1
    for key in ("generated_at", "range_days", "goals", "body_metrics",
                "exercises", "activity"):
        assert key in payload

    bench = next(e for e in payload["exercises"] if e["name"] == "Bench Press")
    assert bench["sessions"][0]["date"] == _d(0)  # newest first
    assert bench["sessions"][0]["weight_kg"] == 62.5

    assert payload["activity"]["visits"] == 2
    assert payload["activity"]["walks"] == 1
    assert payload["goals"]["goal_type"] == "maintain"


def test_build_export_filters_by_date_range(app, user):
    from gymapp.export_ai import build_export

    db.log_exercise(user["id"], "2020-01-01", "Old Lift", 10.0, 5, 3)
    db.log_exercise(user["id"], localtime.today().isoformat(), "New Lift", 20.0, 5, 3)
    payload = build_export(user["id"], db, days=30)
    names = [e["name"] for e in payload["exercises"]]
    assert "New Lift" in names
    assert "Old Lift" not in names


def test_build_export_empty_state(app, user):
    from gymapp.export_ai import build_export

    payload = build_export(user["id"], db, days=30)
    assert payload["exercises"] == []
    assert payload["activity"]["visits"] == 0


def test_to_json_is_valid_and_stable(app, user):
    from gymapp.export_ai import build_export, to_json

    _seed_rich_history(user)
    payload = build_export(user["id"], db, days=90)
    text = to_json(payload)
    parsed = json.loads(text)
    assert parsed == payload  # lossless round-trip


def test_to_markdown_wraps_system_prompt(app, user):
    from gymapp.export_ai import build_export, to_markdown

    _seed_rich_history(user)
    md = to_markdown(build_export(user["id"], db, days=90))
    assert md.startswith("# Gym Progress Report")
    assert "conditioning coach" in md.lower()
    for section in ("## Goals", "## Body Metrics", "## Exercise History",
                    "## Activity"):
        assert section in md
    assert "Bench Press" in md
    assert "62.5" in md


def test_to_markdown_empty_state(app, user):
    from gymapp.export_ai import build_export, to_markdown

    md = to_markdown(build_export(user["id"], db, days=30))
    assert "No exercise history" in md
    assert "No body metrics" in md


def test_to_markdown_is_token_efficient(app, user):
    """The Markdown must be substantially shorter than the raw JSON dump."""
    from gymapp.export_ai import build_export, to_json, to_markdown

    _seed_rich_history(user)
    payload = build_export(user["id"], db, days=90)
    assert len(to_markdown(payload)) < len(to_json(payload))


# ---- route/integration tests -----------------------------------------------


def test_export_ai_json_route(logged_in, user):
    _seed_rich_history(user)
    r = logged_in.get("/export/ai.json")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    parsed = json.loads(r.get_data(as_text=True))
    assert parsed["format_version"] == 1


def test_export_ai_markdown_route(logged_in, user):
    _seed_rich_history(user)
    r = logged_in.get("/export/ai.md")
    assert r.status_code == 200
    assert r.headers["Content-Disposition"].endswith('filename="gym-progress-ai.md"')
    assert r.get_data(as_text=True).startswith("# Gym Progress Report")


def test_export_ai_respects_days_param(logged_in, user):
    db.log_exercise(user["id"], "2020-01-01", "Old Lift", 10.0, 5, 3)
    r = logged_in.get("/export/ai.json?days=30")
    names = [e["name"] for e in r.get_json()["exercises"]]
    assert "Old Lift" not in names


def test_export_ai_rejects_bad_days(logged_in):
    r = logged_in.get("/export/ai.json?days=abc")
    assert r.status_code == 400


def test_export_ai_requires_login(client):
    for path in ("/export/ai.md", "/export/ai.json"):
        r = client.get(path)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


def test_dashboard_links_to_ai_export(logged_in):
    r = logged_in.get("/dashboard")
    assert b"export/ai.md" in r.data
    assert b"export/ai.json" in r.data
