"""Regression tests for body-metric tracking (tracker + metrics CRUD)."""
from gymapp import db


def test_tracker_page_renders(logged_in):
    r = logged_in.get("/tracker")
    assert r.status_code == 200


def test_add_log_and_it_appears(logged_in, user):
    r = logged_in.post(
        "/tracker/add",
        data={"log_date": "2025-01-10", "metric_key": "weight_kg", "value": "80.5"},
    )
    assert r.status_code == 302
    logs = db.list_logs(user["id"])
    assert len(logs) == 1
    assert logs[0]["value"] == 80.5
    assert logs[0]["metric_key"] == "weight_kg"


def test_add_log_ajax_returns_json(logged_in, user):
    r = logged_in.post(
        "/tracker/add",
        data={"log_date": "2025-01-10", "metric_key": "weight_kg", "value": "80.5"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["log"]["value"] == 80.5


def test_add_log_rejects_non_numeric(logged_in, user):
    r = logged_in.post(
        "/tracker/add",
        data={"log_date": "2025-01-10", "metric_key": "weight_kg", "value": "abc"},
    )
    assert r.status_code == 302


def test_add_log_rejects_unknown_metric(logged_in, user):
    r = logged_in.post(
        "/tracker/add",
        data={"log_date": "2025-01-10", "metric_key": "nope", "value": "1"},
    )
    assert r.status_code == 302
    assert db.list_logs(user["id"]) == []


def test_delete_log(logged_in, user):
    log_id = db.add_log(user["id"], "2025-01-10", "weight_kg", 81.0)
    r = logged_in.post(f"/tracker/{log_id}/delete")
    assert r.status_code == 302
    assert db.list_logs(user["id"]) == []


def test_history_json(logged_in, user):
    db.add_log(user["id"], "2025-01-01", "weight_kg", 82.0)
    db.add_log(user["id"], "2025-01-10", "weight_kg", 80.0)
    r = logged_in.get("/tracker/history/weight_kg")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["metric"] == "weight_kg"
    assert [p["value"] for p in payload["points"]] == [82.0, 80.0]


def test_metrics_page_lists_defaults(logged_in):
    r = logged_in.get("/metrics")
    assert r.status_code == 200
    assert b"Weight" in r.data


def test_add_metric_def(logged_in, user):
    r = logged_in.post(
        "/metrics/add",
        data={"metric_key": "neck_cm", "label": "Neck", "unit": "cm"},
    )
    assert r.status_code == 302
    keys = [row["metric_key"] for row in db.list_metric_defs(user["id"])]
    assert "neck_cm" in keys


def test_add_metric_def_rejects_bad_key(logged_in, user):
    logged_in.post("/metrics/add", data={"metric_key": "9bad", "label": "X"})
    keys = [row["metric_key"] for row in db.list_metric_defs(user["id"])]
    assert "9bad" not in keys


def test_delete_metric_deletes_history_too(logged_in, user):
    db.add_log(user["id"], "2025-01-01", "chest_cm", 100.0)
    r = logged_in.post("/metrics/chest_cm/delete")
    assert r.status_code == 302
    assert db.list_logs(user["id"]) == []
    keys = [row["metric_key"] for row in db.list_metric_defs(user["id"])]
    assert "chest_cm" not in keys


def test_export_logs_csv(logged_in, user):
    db.add_log(user["id"], "2025-01-10", "weight_kg", 80.0, "note here")
    r = logged_in.get("/export/logs.csv")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    body = r.get_data(as_text=True)
    assert "weight_kg" in body
    assert "80.0" in body


def test_export_logs_csv_requires_login(client):
    r = client.get("/export/logs.csv")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
