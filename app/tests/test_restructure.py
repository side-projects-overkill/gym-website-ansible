"""Landing page at /, guide merged into Today (golden rules + rest timer)."""
from gymapp import paths

RULES_YAML = """site:
  title: "My Plan"
  rules:
    - "Stop 1-2 reps before failure."
    - "Hydrate between sets."
days:
  - name: "Day 1"
    exercises:
      - name: "Goblet Squat"
        sets_reps: "3 x 10"
        rest: "90s"
"""


def _write_config(user, text=RULES_YAML):
    paths.ensure_user_files(user["id"])
    with open(paths.user_config_path(user["id"]), "w") as fh:
        fh.write(text)


def test_landing_page_for_visitors(client):
    r = client.get("/")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert 'href="/register"' in html and 'href="/login"' in html


def test_root_sends_members_to_today(logged_in):
    r = logged_in.get("/")
    assert r.status_code == 302 and "/dashboard" in r.headers["Location"]


def test_guide_redirects_to_today(logged_in, client):
    r = logged_in.get("/guide")
    assert r.status_code == 302 and "/dashboard" in r.headers["Location"]


def test_guide_requires_login(client):
    r = client.get("/guide")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_nav_has_no_separate_guide_link(logged_in):
    assert 'href="/guide"' not in logged_in.get("/dashboard").get_data(as_text=True)


def test_session_endpoint_removed(client):
    assert client.get("/session").status_code == 404


def test_golden_rules_render_on_today_and_plan(logged_in, user):
    _write_config(user)
    for path in ("/dashboard", "/plan"):
        html = logged_in.get(path).get_data(as_text=True)
        assert 'class="card rules-card' in html, path
        assert "Hydrate between sets." in html, path


def test_no_rules_card_without_rules(logged_in, user):
    _write_config(user, RULES_YAML.replace('  rules:\n    - "Stop 1-2 reps before failure."\n    - "Hydrate between sets."\n', ""))
    assert "rules-card" not in logged_in.get("/plan").get_data(as_text=True)


def test_rules_must_be_a_list_of_strings():
    import pytest
    from gymapp import workout_config
    with pytest.raises(workout_config.ConfigError):
        workout_config.validate("site:\n  rules: nope\ndays: []\n")


def test_quick_log_form_carries_rest_seconds(logged_in, user):
    _write_config(user)
    html = logged_in.get("/plan").get_data(as_text=True)
    assert 'data-rest-seconds="90"' in html


def test_parse_rest_seconds():
    from gymapp.workout_config import parse_rest_seconds as p
    assert p("90s") == 90
    assert p("2 min") == 120
    assert p("60-90s") == 90
    assert p("1:30") == 90
    assert p("") is None and p(None) is None and p("as needed") is None
