"""Import workouts, walks and weight from watch/phone health exports.

Supported uploads (no companion app needed):

- Apple Health: `export.zip` (Health app -> profile -> Export All Health Data)
  or the `export.xml` inside it.
- Google: a Takeout zip containing Fitbit data ("Global Export Data") and/or
  Google Fit data ("Fit/All Sessions", "Fit/Activities/*.tcx").
- Any watch: single `.tcx` or `.gpx` workout files.

Everything is normalised to one shape - per local calendar day:
  walks   {date: {"km": float, "min": float}}   (several walks on a day merge)
  gym     {date, ...}                            (strength-type workouts)
  weights {date: kg}                             (last reading of the day)

Safety: uploads are parsed as streams (Apple exports can be hundreds of MB),
zip members are size-capped while reading (zip-bomb guard), XML goes through
expat with no external entity resolution, and only the summary above is ever
kept - the uploaded file itself is discarded after parsing.
"""
import io
import json
import math
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
from xml.parsers import expat

from . import db, localtime

MAX_MEMBER_BYTES = 2 * 1024 ** 3     # biggest single file we'll read out of a zip
MAX_SMALL_FILE_BYTES = 50 * 1024 ** 2  # JSON / TCX / GPX members
MAX_ZIP_MEMBERS = 50_000
CHUNK = 1024 * 1024

WEIGHT_METRIC = "weight_kg"

# Workout types -> our two buckets. Anything else is reported as skipped.
APPLE_WALK = {"Walking", "Hiking"}
APPLE_GYM = {"TraditionalStrengthTraining", "FunctionalStrengthTraining",
             "HighIntensityIntervalTraining", "CrossTraining", "CoreTraining"}
FITBIT_WALK = {"walk", "hike", "outdoor walk", "treadmill walk"}
FITBIT_GYM = {"weights", "weight training", "workout", "strength training",
              "circuit training", "interval workout", "crossfit", "hiit"}
GFIT_WALK = {"walking", "walking.fitness", "walking.treadmill", "walking.nordic", "hiking"}
GFIT_GYM = {"strength_training", "weightlifting", "crossfit", "high_intensity_interval_training",
            "circuit_training", "calisthenics"}
GPX_WALK_TYPES = {"walking", "walk", "hiking", "hike"}
WALK_MAX_KMH = 7.0  # untyped GPX tracks at or below this speed count as walks


class ImportError_(Exception):
    """User-facing import problem (bad/unsupported/oversized file)."""


@dataclass
class ImportResult:
    source: str = ""
    walks: dict = field(default_factory=dict)
    gym: set = field(default_factory=set)
    weights: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)

    def is_empty(self):
        return not (self.walks or self.gym or self.weights)

    def since(self, date_iso):
        return ImportResult(
            source=self.source,
            walks={d: v for d, v in self.walks.items() if d >= date_iso},
            gym={d for d in self.gym if d >= date_iso},
            weights={d: v for d, v in self.weights.items() if d >= date_iso},
            skipped=self.skipped,
        )

    def date_range(self):
        dates = sorted(set(self.walks) | self.gym | set(self.weights))
        return (dates[0], dates[-1]) if dates else (None, None)

    def to_json(self):
        return json.dumps({"source": self.source, "walks": self.walks, "gym": sorted(self.gym),
                           "weights": self.weights, "skipped": self.skipped})

    @classmethod
    def from_json(cls, text):
        d = json.loads(text)
        return cls(d["source"], d["walks"], set(d["gym"]), d["weights"], d["skipped"])


class _Collector:
    """Accumulates raw activities and rounds them into an ImportResult."""

    def __init__(self, source):
        self.source = source
        self._walks = {}
        self._gym = set()
        self._weights = {}   # date -> (sort_key, kg)
        self._skipped = Counter()

    def walk(self, day, km, minutes):
        cur = self._walks.setdefault(day, [0.0, 0.0])
        cur[0] += km or 0.0
        cur[1] += minutes or 0.0

    def gym(self, day):
        self._gym.add(day)

    def weight(self, day, kg, sort_key=""):
        prev = self._weights.get(day)
        if prev is None or sort_key >= prev[0]:
            self._weights[day] = (sort_key, kg)

    def skip(self, kind):
        self._skipped[kind or "Other"] += 1

    def result(self):
        return ImportResult(
            source=self.source,
            walks={d: {"km": round(k, 2), "min": round(m, 1)} for d, (k, m) in sorted(self._walks.items())},
            gym=set(self._gym),
            weights={d: round(kg, 1) for d, (_, kg) in sorted(self._weights.items())},
            skipped=dict(self._skipped),
        )


# ----------------------------------------------------------------- helpers --

def _to_km(value, unit):
    unit = (unit or "km").lower()
    if unit in ("mi", "mile", "miles"):
        return value * 1.609344
    if unit in ("m", "meter", "meters"):
        return value / 1000
    return value


def _to_min(value, unit):
    unit = (unit or "min").lower()
    if unit in ("hr", "h", "hour", "hours"):
        return value * 60
    if unit in ("s", "sec", "seconds"):
        return value / 60
    return value


def _to_kg(value, unit):
    return value * 0.45359237 if (unit or "kg").lower() in ("lb", "lbs", "pound", "pounds") else value


def _local_day_from_utc(iso):
    """'2024-06-08T12:30:00.000Z' -> local calendar date in APP_TIMEZONE."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(localtime._zone(localtime._configured_tz_name())).date().isoformat()


def _fitbit_day(mmddyy):
    return datetime.strptime(mmddyy.split(" ")[0], "%m/%d/%y").date().isoformat()


class _LimitedReader(io.RawIOBase):
    """Wraps a stream and fails once more than `limit` bytes are read - the
    zip header's declared size can lie, so we enforce while decompressing."""

    def __init__(self, stream, limit):
        self._s, self._left = stream, limit

    def readable(self):
        return True

    def readinto(self, b):
        data = self._s.read(min(len(b), self._left + 1))
        if len(data) > self._left:
            raise ImportError_("A file inside the upload is too large to import.")
        self._left -= len(data)
        b[: len(data)] = data
        return len(data)


def _read_small(stream, limit=None):
    limit = limit or MAX_SMALL_FILE_BYTES
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ImportError_("A file inside the upload is too large to import.")
    return data


def _local(tag):
    return tag.rsplit("}", 1)[-1]


# ---------------------------------------------------------------- parsers --

def _parse_apple(stream, col):
    """Stream-parse Apple's export.xml with expat (fast, low memory)."""
    workout = {}

    def start(name, attrs):
        if name == "Workout":
            workout.clear()
            workout.update(attrs)
            workout["_dist_km"] = None
        elif name == "WorkoutStatistics" and workout:
            if attrs.get("type") in ("HKQuantityTypeIdentifierDistanceWalkingRunning",
                                     "HKQuantityTypeIdentifierDistanceCycling") and attrs.get("sum"):
                workout["_dist_km"] = _to_km(float(attrs["sum"]), attrs.get("unit"))
        elif name == "Record" and attrs.get("type") == "HKQuantityTypeIdentifierBodyMass":
            try:
                kg = _to_kg(float(attrs["value"]), attrs.get("unit"))
            except (KeyError, ValueError):
                return
            start_date = attrs.get("startDate", "")
            col.weight(start_date[:10], kg, start_date)

    def end(name):
        if name != "Workout" or not workout:
            return
        kind = workout.get("workoutActivityType", "").replace("HKWorkoutActivityType", "")
        day = workout.get("startDate", "")[:10]
        if kind in APPLE_WALK:
            km = workout["_dist_km"]
            if km is None and workout.get("totalDistance"):
                km = _to_km(float(workout["totalDistance"]), workout.get("totalDistanceUnit"))
            minutes = _to_min(float(workout.get("duration") or 0), workout.get("durationUnit"))
            col.walk(day, km, minutes)
        elif kind in APPLE_GYM:
            col.gym(day)
        else:
            col.skip(kind)
        workout.clear()

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        while True:
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except expat.ExpatError as exc:
        raise ImportError_(f"The Apple Health file looks damaged ({exc}).") from exc


def _parse_fitbit_exercise(data, col):
    for item in json.loads(data):
        name = (item.get("activityName") or "").strip()
        try:
            day = _fitbit_day(item["startTime"])
        except (KeyError, ValueError):
            continue
        if name.lower() in FITBIT_WALK:
            km = _to_km(float(item["distance"]), item.get("distanceUnit")) if item.get("distance") else None
            col.walk(day, km, (item.get("duration") or 0) / 60000)
        elif name.lower() in FITBIT_GYM:
            col.gym(day)
        else:
            col.skip(name)


def _parse_fitbit_weight(data, col, weight_unit):
    for item in json.loads(data):
        try:
            day = _fitbit_day(item["date"])
            kg = _to_kg(float(item["weight"]), weight_unit)
        except (KeyError, ValueError):
            continue
        col.weight(day, kg, f"{day} {item.get('time', '')}")


def _parse_gfit_session(data, col):
    s = json.loads(data)
    kind = (s.get("fitnessActivity") or "").lower()
    try:
        day = _local_day_from_utc(s["startTime"])
    except (KeyError, ValueError):
        return
    if kind in GFIT_WALK:
        minutes = float(str(s.get("duration", "0")).rstrip("s") or 0) / 60
        meters = sum(a.get("floatValue", 0) for a in s.get("aggregate", [])
                     if a.get("metricName") == "com.google.distance.delta")
        col.walk(day, meters / 1000 if meters else None, minutes)
    elif kind in GFIT_GYM:
        col.gym(day)
    else:
        col.skip(kind)


def _parse_tcx(data, col):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportError_("A TCX file could not be read.") from exc
    for act in root.iter():
        if _local(act.tag) != "Activity":
            continue
        sport = act.get("Sport", "Other")
        start = next((e.text for e in act if _local(e.tag) == "Id"), None)
        if not start:
            continue
        secs = meters = 0.0
        for lap in act:
            if _local(lap.tag) != "Lap":
                continue
            for e in lap:
                if _local(e.tag) == "TotalTimeSeconds":
                    secs += float(e.text or 0)
                elif _local(e.tag) == "DistanceMeters":
                    meters += float(e.text or 0)
        if sport.lower() == "walking":
            col.walk(_local_day_from_utc(start), meters / 1000, secs / 60)
        else:
            col.skip(sport)


def _haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _parse_gpx(data, col):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportError_("A GPX file could not be read.") from exc
    for trk in root.iter():
        if _local(trk.tag) != "trk":
            continue
        kind = next(((e.text or "").strip().lower() for e in trk if _local(e.tag) == "type"), "")
        points, times = [], []
        for pt in trk.iter():
            if _local(pt.tag) != "trkpt":
                continue
            points.append((float(pt.get("lat")), float(pt.get("lon"))))
            t = next((e.text for e in pt if _local(e.tag) == "time"), None)
            if t:
                times.append(t)
        if len(points) < 2 or len(times) < 2:
            continue
        km = sum(_haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))
        t0 = datetime.fromisoformat(times[0].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))
        minutes = (t1 - t0).total_seconds() / 60
        is_walk = kind in GPX_WALK_TYPES or (not kind and minutes > 0 and km / (minutes / 60) <= WALK_MAX_KMH)
        if is_walk:
            col.walk(_local_day_from_utc(times[0]), km, minutes)
        else:
            col.skip(kind or "Fast track")


# ------------------------------------------------------------------ entry --

def _parse_zip(fileobj, weight_unit):
    try:
        zf = zipfile.ZipFile(fileobj)
    except zipfile.BadZipFile as exc:
        raise ImportError_("That zip file couldn't be opened.") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ImportError_("That zip has too many files to import.")
        names = [i.filename for i in infos]

        apple = next((i for i in infos if os.path.basename(i.filename) == "export.xml"), None)
        if apple:
            if apple.file_size > MAX_MEMBER_BYTES:
                raise ImportError_("The Apple Health export is too large to import.")
            col = _Collector("Apple Health")
            with zf.open(apple) as raw:
                _parse_apple(io.BufferedReader(_LimitedReader(raw, MAX_MEMBER_BYTES)), col)
            return col.result()

        fitbit = [i for i in infos if "Global Export Data/" in i.filename and i.filename.endswith(".json")]
        gfit_sessions = [i for i in infos if "/Fit/All Sessions/" in "/" + i.filename and i.filename.endswith(".json")]
        tracks = [i for i in infos if i.filename.lower().endswith((".tcx", ".gpx"))]

        if fitbit:
            col = _Collector("Google (Fitbit)")
            for i in fitbit:
                base = os.path.basename(i.filename)
                if base.startswith("exercise-"):
                    _parse_fitbit_exercise(_read_small(zf.open(i)), col)
                elif base.startswith("weight-"):
                    _parse_fitbit_weight(_read_small(zf.open(i)), col, weight_unit)
            return col.result()

        if gfit_sessions:
            col = _Collector("Google Fit")
            for i in gfit_sessions:
                _parse_gfit_session(_read_small(zf.open(i)), col)
            return col.result()

        if tracks:
            col = _Collector("Workout files")
            for i in tracks:
                data = _read_small(zf.open(i))
                (_parse_tcx if i.filename.lower().endswith(".tcx") else _parse_gpx)(data, col)
            return col.result()

        del names
    raise ImportError_("No Apple Health, Fitbit, Google Fit, TCX or GPX data found in that zip.")


def parse_upload(fileobj, filename, weight_unit="kg"):
    """Parse an uploaded file into an ImportResult. Raises ImportError_."""
    name = (filename or "").lower()
    if name.endswith(".zip"):
        result = _parse_zip(fileobj, weight_unit)
    elif name.endswith(".xml"):
        col = _Collector("Apple Health")
        _parse_apple(io.BufferedReader(_LimitedReader(fileobj, MAX_MEMBER_BYTES)), col)
        result = col.result()
    elif name.endswith(".tcx"):
        col = _Collector("Workout files")
        _parse_tcx(_read_small(fileobj), col)
        result = col.result()
    elif name.endswith(".gpx"):
        col = _Collector("Workout files")
        _parse_gpx(_read_small(fileobj), col)
        result = col.result()
    else:
        raise ImportError_("Upload an Apple Health export (.zip/.xml), a Google Takeout .zip, or a .tcx/.gpx file.")
    return result


# ------------------------------------------------------------ applying it --

def _existing(user_id):
    return (set(db.visit_dates(user_id)), set(db.walk_dates(user_id)),
            set(db.log_dates(user_id, WEIGHT_METRIC)))


def preview_counts(user_id, result):
    """How many entries would actually be added (days already logged are kept as-is)."""
    visits, walks, weights = _existing(user_id)
    return {
        "walks": len(set(result.walks) - walks),
        "gym": len(result.gym - visits),
        "weights": len(set(result.weights) - weights),
    }


def apply(user_id, result):
    """Write new days into the tracker. Never overwrites a day you logged yourself."""
    note = f"Imported from {result.source}"
    visits, walks, weights = _existing(user_id)
    added = {"walks": 0, "gym": 0, "weights": 0}
    for day, w in result.walks.items():
        if day not in walks and db.checkin_walk(user_id, day, w["km"] or None, w["min"] or None, note):
            added["walks"] += 1
    for day in sorted(result.gym):
        if day not in visits and db.checkin_visit(user_id, day, note):
            added["gym"] += 1
    if result.weights and not any(d["metric_key"] == WEIGHT_METRIC for d in db.list_metric_defs(user_id)):
        db.add_metric_def(user_id, WEIGHT_METRIC, "Weight", "kg", 0)
    for day, kg in result.weights.items():
        if day not in weights:
            db.add_log(user_id, day, WEIGHT_METRIC, kg, note)
            added["weights"] += 1
    return added


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
