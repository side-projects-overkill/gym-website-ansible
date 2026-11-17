"""Regression tests for attendance + walking check-ins."""


def test_attendance_page(logged_in):
    r = logged_in.get("/attendance")
    assert r.status_code == 200


def test_checkin_today_creates_visit(logged_in, user):
    from gymapp import db, localtime

    r = logged_in.post("/attendance/checkin")
    assert r.status_code == 302
    dates = [row["visit_date"] for row in db.list_recent_visits(user["id"])]
    assert localtime.today().isoformat() in dates


def test_checkin_today_ajax(logged_in, user):
    r = logged_in.post(
        "/attendance/checkin", headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    # second check-in should report already-checked-in
    r2 = logged_in.post(
        "/attendance/checkin", headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert r2.get_json()["ok"] is False


def test_add_past_visit(logged_in, user):
    from gymapp import db

    r = logged_in.post("/attendance/add", data={"visit_date": "2024-06-01"})
    assert r.status_code == 302
    dates = [row["visit_date"] for row in db.list_recent_visits(user["id"])]
    assert "2024-06-01" in dates


def test_add_future_visit_rejected(logged_in, user):
    from gymapp import db, localtime

    future = (localtime.today().replace(month=12, day=28)).isoformat()
    logged_in.post("/attendance/add", data={"visit_date": "2999-01-01"})
    dates = [row["visit_date"] for row in db.list_recent_visits(user["id"])]
    assert "2999-01-01" not in dates


def test_add_invalid_date_rejected(logged_in, user):
    r = logged_in.post("/attendance/add", data={"visit_date": "not-a-date"})
    assert r.status_code == 302


def test_delete_visit(logged_in, user):
    from gymapp import db

    db.checkin_visit(user["id"], "2024-06-01")
    r = logged_in.post("/attendance/2024-06-01/delete")
    assert r.status_code == 302
    dates = [row["visit_date"] for row in db.list_recent_visits(user["id"])]
    assert "2024-06-01" not in dates


# ---- walking ---------------------------------------------------------------


def test_walking_page(logged_in):
    r = logged_in.get("/walking")
    assert r.status_code == 200


def test_walk_checkin_ajax(logged_in, user):
    r = logged_in.post(
        "/walking/checkin", headers={"X-Requested-With": "XMLHttpRequest"}
    )
    assert r.get_json()["ok"] is True


def test_add_walk_with_distance(logged_in, user):
    from gymapp import db

    logged_in.post(
        "/walking/add",
        data={"walk_date": "2024-06-01", "distance_km": "5.2", "duration_min": "45"},
    )
    walks = db.list_recent_walks(user["id"])
    assert len(walks) == 1
    assert walks[0]["distance_km"] == 5.2
    assert walks[0]["duration_min"] == 45.0


def test_add_walk_rejects_bad_distance(logged_in, user):
    from gymapp import db

    logged_in.post(
        "/walking/add", data={"walk_date": "2024-06-01", "distance_km": "abc"}
    )
    assert db.list_recent_walks(user["id"]) == []


def test_delete_walk(logged_in, user):
    from gymapp import db

    db.checkin_walk(user["id"], "2024-06-01", 3.0)
    logged_in.post("/walking/2024-06-01/delete")
    assert db.list_recent_walks(user["id"]) == []
