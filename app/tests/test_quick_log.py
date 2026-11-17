"""Feature C - 'Repeat Last' quick-log button (TDD: written RED first)."""
from datetime import timedelta

from gymapp import db, localtime


def _d(days_ago):
    return (localtime.today() - timedelta(days=days_ago)).isoformat()


def _login_and_open_plan(logged_in, user):
    logged_in.get("/plan")  # seed default config
    db.log_exercise(user["id"], _d(2), "Flat DB Bench Press", 60.0, 8, 3)
    return logged_in.get("/plan")


def test_repeat_button_renders_with_last_values(logged_in, user):
    r = _login_and_open_plan(logged_in, user)
    html = r.get_data(as_text=True)
    assert "exercise-repeat" in html
    # data attributes carry the last weight/reps so JS can prefill
    assert 'data-weight="60.0"' in html
    assert 'data-reps="8"' in html


def test_repeat_button_absent_for_unlogged_exercises(logged_in, user):
    logged_in.get("/plan")  # seed; nothing logged
    r = logged_in.get("/plan")
    assert "exercise-repeat" not in r.get_data(as_text=True)


def test_repeat_button_renders_on_dashboard_too(logged_in, user):
    logged_in.get("/plan")
    db.log_exercise(user["id"], _d(2), "Flat DB Bench Press", 60.0, 8, 3)
    r = logged_in.get("/dashboard")
    assert "exercise-repeat" in r.get_data(as_text=True)


def test_repeat_js_ships(logged_in, user):
    """The static JS bundle contains the prefill handler."""
    r = logged_in.get("/static/ajax-forms.js")
    assert b"exercise-repeat" in r.get_data()


def test_repeat_only_prefills_no_submit(logged_in, user):
    """The repeat button must be type=button so it never submits the form."""
    r = _login_and_open_plan(logged_in, user)
    import re

    html = r.get_data(as_text=True)
    btns = re.findall(r"<button[^>]*exercise-repeat[^>]*>", html)
    assert btns
    for btn in btns:
        assert 'type="button"' in btn
