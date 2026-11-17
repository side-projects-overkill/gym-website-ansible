"""Feature B - deterministic smart-insight engine (TDD: written RED first).

Rules: stalled-weight plateau detection, weekly volume trends,
attendance gaps vs. goal, and graceful fallback when no external AI
endpoint is configured.
"""
from datetime import timedelta

from gymapp import db, localtime


def _d(days_ago):
    return (localtime.today() - timedelta(days=days_ago)).isoformat()


def _stall_seed(user, days=(20, 13, 6)):
    for offset in days:
        db.log_exercise(user["id"], _d(offset), "Bench Press", 60.0, 8, 3)


# ---- rule: stalled weights ---------------------------------------------------


def test_detects_stalled_weight(app, user):
    from gymapp.insights import compute_insights

    _stall_seed(user)
    insights = compute_insights(user["id"], db)
    stall = next((i for i in insights if i["type"] == "plateau"), None)
    assert stall is not None
    assert "Bench Press" in stall["title"]
    assert "60" in stall["detail"]


def test_no_plateau_when_progressing(app, user):
    from gymapp.insights import compute_insights

    for i, offset in enumerate((20, 13, 6)):
        db.log_exercise(user["id"], _d(offset), "Squat", 100.0 + i * 2.5, 8, 3)
    insights = compute_insights(user["id"], db)
    assert not any(i["type"] == "plateau" for i in insights)


def test_no_plateau_with_under_3_sessions(app, user):
    from gymapp.insights import compute_insights

    db.log_exercise(user["id"], _d(6), "Row", 50.0, 8, 3)
    db.log_exercise(user["id"], _d(3), "Row", 50.0, 8, 3)
    assert not any(i["type"] == "plateau" for i in compute_insights(user["id"], db))


def test_no_plateau_when_reps_vary(app, user):
    from gymapp.insights import compute_insights

    for i, offset in enumerate((20, 13, 6)):
        db.log_exercise(user["id"], _d(offset), "Curl", 20.0, 8 + i, 3)
    assert not any(i["type"] == "plateau" for i in compute_insights(user["id"], db))


# ---- rule: weekly volume trend -----------------------------------------------


def test_detects_volume_spike(app, user):
    from gymapp.insights import compute_insights

    # last week: 3 sessions of 100kg x 10 x 3 = 3000 each
    for offset in (6, 4, 2):
        db.log_exercise(user["id"], _d(offset), "Squat", 100.0, 10, 3)
    # prior week: 1 session only
    db.log_exercise(user["id"], _d(13), "Squat", 100.0, 10, 3)

    insights = compute_insights(user["id"], db)
    spike = next((i for i in insights if i["type"] == "volume_spike"), None)
    assert spike is not None
    assert spike["severity"] == "warning"


def test_detects_volume_drop(app, user):
    from gymapp.insights import compute_insights

    for offset in (13, 11, 9):
        db.log_exercise(user["id"], _d(offset), "Squat", 100.0, 10, 3)
    db.log_exercise(user["id"], _d(3), "Squat", 100.0, 10, 3)

    insights = compute_insights(user["id"], db)
    drop = next((i for i in insights if i["type"] == "volume_drop"), None)
    assert drop is not None


def test_no_volume_flag_when_steady(app, user):
    from gymapp.insights import compute_insights

    for offset in (13, 11, 6, 4, 2):
        db.log_exercise(user["id"], _d(offset), "Squat", 100.0, 10, 3)
    assert not any(
        i["type"] in ("volume_spike", "volume_drop")
        for i in compute_insights(user["id"], db)
    )


def test_no_volume_flag_with_no_last_week_data(app, user):
    from gymapp.insights import compute_insights

    for offset in (6, 4):
        db.log_exercise(user["id"], _d(offset), "Squat", 100.0, 10, 3)
    assert not any(
        i["type"] in ("volume_spike", "volume_drop")
        for i in compute_insights(user["id"], db)
    )


# ---- rule: attendance gap -----------------------------------------------------


def test_detects_attendance_gap(app, user):
    from gymapp.insights import compute_insights

    db.checkin_visit(user["id"], _d(10))
    insights = compute_insights(user["id"], db)
    gap = next((i for i in insights if i["type"] == "attendance_gap"), None)
    assert gap is not None
    assert gap["severity"] == "info"


def test_no_gap_when_recently_visited(app, user):
    from gymapp.insights import compute_insights

    db.checkin_visit(user["id"], _d(1))
    assert not any(
        i["type"] == "attendance_gap" for i in compute_insights(user["id"], db)
    )


# ---- structure + fallback ------------------------------------------------------


def test_insight_structure(app, user):
    from gymapp.insights import compute_insights

    _stall_seed(user)
    for i in compute_insights(user["id"], db):
        assert set(i) == {"type", "severity", "title", "detail"}
        assert i["severity"] in ("info", "warning")


def test_insights_empty_when_no_data(app, user):
    from gymapp.insights import compute_insights

    assert compute_insights(user["id"], db) == []


def test_dashboard_shows_insights_card(logged_in, user):
    _stall_seed(user)
    r = logged_in.get("/dashboard")
    assert b"Coach Insights" in r.data
    assert b"Bench Press" in r.data


def test_dashboard_insights_card_handles_empty(logged_in, user):
    r = logged_in.get("/dashboard")
    assert r.status_code == 200
    assert b"Coach Insights" in r.data


def test_ai_coach_fallback_without_api_key(app, user):
    """With no AI endpoint configured, the coach degrades gracefully to
    the deterministic insights (no exception, no network call)."""
    from gymapp.insights import ai_coach_summary

    app.config.pop("AI_ENDPOINT", None)
    _stall_seed(user)
    summary = ai_coach_summary(user["id"], db, app)
    assert summary is not None  # deterministic fallback text
