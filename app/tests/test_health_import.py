"""Watch data import: Apple Health export, Google (Fitbit Takeout + Google Fit
Takeout), and plain GPX/TCX workout files."""
import io
import json
import re
import zipfile

import pytest

from gymapp import db, health_import

# ---------------------------------------------------------------- fixtures --

APPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (Record*, Workout*)>
]>
<HealthData locale="en_IN">
 <Record type="HKQuantityTypeIdentifierStepCount" unit="count" value="900" startDate="2024-06-01 08:00:00 +0530" endDate="2024-06-01 08:10:00 +0530"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" unit="kg" value="82.4" startDate="2024-06-01 07:00:00 +0530" endDate="2024-06-01 07:00:00 +0530"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" unit="kg" value="82.0" startDate="2024-06-01 21:00:00 +0530" endDate="2024-06-01 21:00:00 +0530"/>
 <Record type="HKQuantityTypeIdentifierBodyMass" unit="lb" value="180" startDate="2024-06-03 07:00:00 +0530" endDate="2024-06-03 07:00:00 +0530"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="32.5" durationUnit="min" totalDistance="2.6" totalDistanceUnit="km" startDate="2024-06-01 18:00:00 +0530" endDate="2024-06-01 18:32:30 +0530"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeWalking" duration="20" durationUnit="min" startDate="2024-06-01 20:00:00 +0530" endDate="2024-06-01 20:20:00 +0530">
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="1.4" unit="km"/>
 </Workout>
 <Workout workoutActivityType="HKWorkoutActivityTypeHiking" duration="1.5" durationUnit="hr" startDate="2024-06-02 06:00:00 +0530" endDate="2024-06-02 07:30:00 +0530">
  <WorkoutStatistics type="HKQuantityTypeIdentifierDistanceWalkingRunning" sum="3" unit="mi"/>
 </Workout>
 <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining" duration="55" durationUnit="min" startDate="2024-06-03 07:30:00 +0530" endDate="2024-06-03 08:25:00 +0530"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeSwimming" duration="30" durationUnit="min" startDate="2024-06-04 07:30:00 +0530" endDate="2024-06-04 08:00:00 +0530"/>
</HealthData>
"""

FITBIT_EXERCISE = [
    {"activityName": "Walk", "startTime": "06/05/24 18:00:00", "duration": 1800000,
     "distance": 2.5, "distanceUnit": "Kilometer"},
    {"activityName": "Weights", "startTime": "06/06/24 07:00:00", "duration": 3000000},
    {"activityName": "Run", "startTime": "06/07/24 07:00:00", "duration": 1500000,
     "distance": 4.0, "distanceUnit": "Kilometer"},
]
FITBIT_WEIGHT = [{"logId": 1, "weight": 81.5, "date": "06/05/24", "time": "07:00:00"}]

GOOGLE_FIT_SESSION = {
    "fitnessActivity": "walking",
    "startTime": "2024-06-08T12:30:00.000Z",
    "endTime": "2024-06-08T13:00:00.000Z",
    "duration": "1800.000s",
    "aggregate": [{"metricName": "com.google.distance.delta", "floatValue": 2200.0}],
}
GOOGLE_FIT_STRENGTH = {
    "fitnessActivity": "strength_training",
    "startTime": "2024-06-09T02:00:00.000Z",
    "endTime": "2024-06-09T03:00:00.000Z",
    "duration": "3600s",
    "aggregate": [],
}

TCX = """<?xml version="1.0"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
 <Activities><Activity Sport="Walking"><Id>2024-06-10T12:00:00Z</Id>
  <Lap StartTime="2024-06-10T12:00:00Z"><TotalTimeSeconds>1500</TotalTimeSeconds><DistanceMeters>1900</DistanceMeters></Lap>
  <Lap StartTime="2024-06-10T12:25:00Z"><TotalTimeSeconds>300</TotalTimeSeconds><DistanceMeters>400</DistanceMeters></Lap>
 </Activity></Activities>
</TrainingCenterDatabase>
"""

GPX = """<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
 <trk><name>Evening walk</name><trkseg>
  <trkpt lat="12.9716" lon="77.5946"><time>2024-06-11T12:00:00Z</time></trkpt>
  <trkpt lat="12.9806" lon="77.5946"><time>2024-06-11T12:15:00Z</time></trkpt>
 </trkseg></trk>
</gpx>
"""


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


# ------------------------------------------------------------------ parsing --

def test_apple_health_xml():
    r = health_import.parse_upload(io.BytesIO(APPLE_XML.encode()), "export.xml")
    assert r.source == "Apple Health"
    # two walks on 06-01 are merged into one day
    assert r.walks["2024-06-01"] == {"km": 4.0, "min": 52.5}
    # hiking counts as a walk, miles and hours converted
    assert r.walks["2024-06-02"] == {"km": 4.83, "min": 90.0}
    assert r.gym == {"2024-06-03"}
    # last weight of the day wins; pounds are converted
    assert r.weights == {"2024-06-01": 82.0, "2024-06-03": 81.6}
    assert r.skipped == {"Swimming": 1}


def test_apple_health_zip_export():
    z = _zip({"apple_health_export/export.xml": APPLE_XML,
              "apple_health_export/export_cda.xml": "<x/>"})
    r = health_import.parse_upload(z, "export.zip")
    assert r.source == "Apple Health" and "2024-06-03" in r.gym


def test_fitbit_takeout():
    z = _zip({
        "Takeout/Fitbit/Global Export Data/exercise-0.json": json.dumps(FITBIT_EXERCISE),
        "Takeout/Fitbit/Global Export Data/weight-2024-06-05.json": json.dumps(FITBIT_WEIGHT),
    })
    r = health_import.parse_upload(z, "takeout.zip")
    assert r.source == "Google (Fitbit)"
    assert r.walks == {"2024-06-05": {"km": 2.5, "min": 30.0}}
    assert r.gym == {"2024-06-06"}
    assert r.weights == {"2024-06-05": 81.5}
    assert r.skipped == {"Run": 1}


def test_fitbit_weight_in_pounds():
    z = _zip({"Takeout/Fitbit/Global Export Data/weight-x.json": json.dumps(
        [{"weight": 180, "date": "06/05/24"}])})
    r = health_import.parse_upload(z, "takeout.zip", weight_unit="lb")
    assert r.weights == {"2024-06-05": 81.6}


def test_google_fit_takeout_sessions_use_local_date(app):
    z = _zip({
        "Takeout/Fit/All Sessions/2024-06-08_walk.json": json.dumps(GOOGLE_FIT_SESSION),
        "Takeout/Fit/All Sessions/2024-06-09_lift.json": json.dumps(GOOGLE_FIT_STRENGTH),
    })
    r = health_import.parse_upload(z, "takeout.zip")
    assert r.source == "Google Fit"
    assert r.walks == {"2024-06-08": {"km": 2.2, "min": 30.0}}
    # 02:00Z on the 9th is 07:30 in Asia/Kolkata, still the 9th
    assert r.gym == {"2024-06-09"}


def test_tcx_file(app):
    r = health_import.parse_upload(io.BytesIO(TCX.encode()), "walk.tcx")
    assert r.walks == {"2024-06-10": {"km": 2.3, "min": 30.0}}


def test_gpx_file_slow_track_is_a_walk(app):
    r = health_import.parse_upload(io.BytesIO(GPX.encode()), "walk.gpx")
    day = r.walks["2024-06-11"]
    assert day["min"] == 15.0 and 0.9 < day["km"] < 1.1


def test_unknown_file_is_rejected():
    with pytest.raises(health_import.ImportError_):
        health_import.parse_upload(io.BytesIO(b"hello"), "notes.txt")


def test_zip_without_health_data_is_rejected():
    with pytest.raises(health_import.ImportError_):
        health_import.parse_upload(_zip({"cat.jpg": "x"}), "photos.zip")


def test_zip_bomb_member_is_rejected(monkeypatch):
    monkeypatch.setattr(health_import, "MAX_MEMBER_BYTES", 1000)
    z = _zip({"apple_health_export/export.xml": APPLE_XML + " " * 5000})
    with pytest.raises(health_import.ImportError_, match="too large"):
        health_import.parse_upload(z, "export.zip")


def test_since_filter():
    r = health_import.parse_upload(io.BytesIO(APPLE_XML.encode()), "export.xml")
    f = r.since("2024-06-03")
    assert set(f.walks) == set() and f.gym == {"2024-06-03"} and set(f.weights) == {"2024-06-03"}


# -------------------------------------------------------------------- apply --

def test_apply_skips_days_already_logged(app, user):
    db.checkin_walk(user["id"], "2024-06-01", 1.0, 10, "manual")
    db.add_log(user["id"], "2024-06-03", "weight_kg", 80.0)
    r = health_import.parse_upload(io.BytesIO(APPLE_XML.encode()), "export.xml")

    preview = health_import.preview_counts(user["id"], r)
    assert preview == {"walks": 1, "gym": 1, "weights": 1}

    added = health_import.apply(user["id"], r)
    assert added == {"walks": 1, "gym": 1, "weights": 1}
    walks = {w["walk_date"]: w for w in db.list_recent_walks(user["id"])}
    assert walks["2024-06-01"]["note"] == "manual"          # untouched
    assert walks["2024-06-02"]["note"] == "Imported from Apple Health"
    # importing again adds nothing
    assert health_import.apply(user["id"], r) == {"walks": 0, "gym": 0, "weights": 0}


# --------------------------------------------------------------------- web --

def _token_from(location):
    return re.search(r"/import/([A-Za-z0-9_-]+)$", location).group(1)


def test_import_requires_login(client):
    assert "/login" in client.get("/import").headers["Location"]


def test_import_flow_upload_preview_confirm(logged_in, user):
    assert b"Apple Health" in logged_in.get("/import").data

    r = logged_in.post("/import", data={
        "file": (io.BytesIO(APPLE_XML.encode()), "export.xml"), "weight_unit": "kg",
    }, content_type="multipart/form-data")
    assert r.status_code == 302
    token = _token_from(r.headers["Location"])

    page = logged_in.get(f"/import/{token}").get_data(as_text=True)
    assert "2 walks" in page and "1 gym" in page

    r = logged_in.post(f"/import/{token}", data={"range": "all"})
    assert r.status_code == 302
    assert len(db.list_recent_walks(user["id"])) == 2
    # the pending import is single-use
    assert logged_in.get(f"/import/{token}").status_code == 404
    # Today shows when we last synced
    assert "Last synced" in logged_in.get("/dashboard").get_data(as_text=True)


def test_pending_import_is_private_to_its_user(logged_in, user, app):
    from tests.conftest import make_user
    r = logged_in.post("/import", data={"file": (io.BytesIO(APPLE_XML.encode()), "export.xml")},
                       content_type="multipart/form-data")
    token = _token_from(r.headers["Location"])
    other = make_user(app, username="someoneelse")
    with logged_in.session_transaction() as sess:
        sess["user_id"] = other["id"]
    assert logged_in.get(f"/import/{token}").status_code == 404


def test_bad_token_is_404(logged_in):
    assert logged_in.get("/import/..%2F..%2Fetc").status_code == 404
