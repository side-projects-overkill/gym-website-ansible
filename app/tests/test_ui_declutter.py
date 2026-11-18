"""UI structure guards for the decluttered layout.

These pin the simplifications (one-row nav with a settings menu, a focused
dashboard, collapsed secondary forms, a compact workout table) so the pages
don't drift back into clutter.
"""
import re


def _html(client, path):
    r = client.get(path)
    assert r.status_code == 200, path
    return r.get_data(as_text=True)


# --- nav -------------------------------------------------------------------

def test_nav_is_single_row_with_settings_menu(logged_in):
    html = _html(logged_in, "/dashboard")
    assert "topnav-links-secondary" not in html
    assert 'class="nav-menu"' in html
    menu = html.split('class="nav-menu"', 1)[1].split("</details>", 1)[0]
    for href in ("/plan/edit", "/foods/edit", "/metrics", "/account/password",
                 "/logout", "/export/logs.csv", "/export/ai.md"):
        assert href in menu, href


def test_primary_nav_has_at_most_eight_links(logged_in):
    html = _html(logged_in, "/dashboard")
    primary = html.split('class="topnav-links-primary"', 1)[1].split("</div>", 1)[0]
    assert len(re.findall(r"<a ", primary)) <= 8


# --- dashboard -------------------------------------------------------------

def test_dashboard_drops_quick_links_grid(logged_in):
    html = _html(logged_in, "/dashboard")
    assert "Quick Links" not in html
    assert "link-grid" not in html


def test_dashboard_tucks_insights_into_collapsible(logged_in):
    html = _html(logged_in, "/dashboard")
    assert 'class="card insights-panel"' in html
    panel = html.split('class="card insights-panel"', 1)[1]
    assert "Coach Insights" in panel


def test_dashboard_has_single_weight_chart(logged_in):
    html = _html(logged_in, "/dashboard")
    assert "trendChart" not in html
    assert "weightSparkline" in html


# --- attendance / walking --------------------------------------------------

def test_attendance_past_visit_form_is_collapsed(logged_in):
    html = _html(logged_in, "/attendance")
    assert '<details class="card collapsible">' in html
    assert "Log a past visit" in html


def test_walking_past_walk_form_is_collapsed(logged_in):
    html = _html(logged_in, "/walking")
    assert '<details class="card collapsible">' in html
    assert "Log a past walk" in html


# --- workout table ---------------------------------------------------------

def test_workout_table_uses_three_columns(logged_in):
    logged_in.get("/plan")  # seed default config
    html = _html(logged_in, "/plan")
    head = html.split("<thead>", 1)[1].split("</thead>", 1)[0]
    assert len(re.findall(r"<th", head)) == 3
