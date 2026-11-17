"""Deterministic smart-insight engine (Feature B).

A small set of plain rules over the existing DB reads - no new tables,
no external services required. Every insight is a dict of
{type, severity, title, detail}, so the dashboard card (and any future
consumer) can render them without knowing the rules.

`ai_coach_summary()` optionally enriches the deterministic output with a
call to an external LLM endpoint, but degrades gracefully to a local
summary whenever no endpoint is configured or the call fails - the app
stays fully functional offline / local-first.
"""
from datetime import timedelta

from . import localtime

VOLUME_SPIKE_RATIO = 1.5
VOLUME_DROP_RATIO = 0.6
PLATEAU_MIN_SESSIONS = 3
ATTENDANCE_GAP_DAYS = 7


def _recent_exercise_rows(db_module, user_id):
    cutoff = (localtime.today() - timedelta(days=60)).isoformat()
    return db_module.get_db().execute(
        "SELECT exercise_name, log_date, weight_kg, reps, sets "
        "FROM exercise_logs WHERE user_id = ? AND log_date >= ? "
        "ORDER BY exercise_name, log_date ASC, id ASC",
        (user_id, cutoff),
    ).fetchall()


def _detect_plateaus(rows_by_name):
    insights = []
    for name, sessions in sorted(rows_by_name.items()):
        if len(sessions) < PLATEAU_MIN_SESSIONS:
            continue
        last = sessions[-PLATEAU_MIN_SESSIONS:]
        weights = [s["weight_kg"] for s in last]
        reps = [s["reps"] for s in last]
        if None in weights or None in reps:
            continue
        if len(set(weights)) == 1 and len(set(reps)) == 1:
            insights.append({
                "type": "plateau",
                "severity": "info",
                "title": f"{name} looks stalled",
                "detail": (
                    f"Same weight ({weights[0]:g}kg) and reps ({reps[0]}) for the "
                    f"last {PLATEAU_MIN_SESSIONS} sessions - consider adding "
                    "weight or reps next time."
                ),
            })
    return insights


def _tonnage(sessions):
    total = 0.0
    for s in sessions:
        if s["weight_kg"] and s["reps"] and s["sets"]:
            total += s["weight_kg"] * s["reps"] * s["sets"]
    return total


def _detect_volume_trend(rows):
    today = localtime.today()
    this_week_start = (today - timedelta(days=6)).isoformat()
    prev_week_start = (today - timedelta(days=13)).isoformat()
    this_week = [r for r in rows if r["log_date"] >= this_week_start]
    prev_week = [
        r for r in rows if prev_week_start <= r["log_date"] < this_week_start
    ]
    this_vol = _tonnage(this_week)
    prev_vol = _tonnage(prev_week)
    if prev_vol <= 0 or this_vol <= 0:
        return []

    ratio = this_vol / prev_vol
    if ratio > VOLUME_SPIKE_RATIO:
        return [{
            "type": "volume_spike",
            "severity": "warning",
            "title": "Big jump in training volume",
            "detail": (
                f"This week's volume is {ratio:.1f}x last week's "
                f"({this_vol:.0f} vs {prev_vol:.0f} kg total). Watch recovery - "
                "consider keeping one lighter session."
            ),
        }]
    if ratio < VOLUME_DROP_RATIO:
        return [{
            "type": "volume_drop",
            "severity": "info",
            "title": "Training volume has dropped",
            "detail": (
                f"This week's volume is only {ratio:.0%} of last week's "
                f"({this_vol:.0f} vs {prev_vol:.0f} kg total). Ease back in "
                "rather than doubling up."
            ),
        }]
    return []


def _detect_attendance_gap(db_module, user_id, user):
    if not user["goal_weekly_visits"]:
        return []
    cutoff = (localtime.today() - timedelta(days=ATTENDANCE_GAP_DAYS)).isoformat()
    row = db_module.get_db().execute(
        "SELECT MAX(visit_date) AS last FROM gym_visits WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    last_visit = row["last"] if row else None
    if last_visit is None:
        return []  # never trained here yet - nothing to nag about
    if last_visit >= cutoff:
        return []
    return [{
        "type": "attendance_gap",
        "severity": "info",
        "title": "No gym visit in over a week",
        "detail": (
            f"Last visit was {last_visit} and your goal is "
            f"{user['goal_weekly_visits']} visits/week - a session today "
            "would get you back on track."
        ),
    }]


def compute_insights(user_id, db_module):
    """All deterministic rules, computed from existing tables. Returns a
    list of insight dicts (may be empty for a fresh account)."""
    user = db_module.get_user(user_id)
    rows = _recent_exercise_rows(db_module, user_id)

    rows_by_name = {}
    for row in rows:
        rows_by_name.setdefault(row["exercise_name"], []).append(row)

    insights = []
    insights.extend(_detect_plateaus(rows_by_name))
    insights.extend(_detect_volume_trend(rows))
    insights.extend(_detect_attendance_gap(db_module, user_id, user))
    return insights


def ai_coach_summary(user_id, db_module, app):
    """Optional LLM enrichment of the deterministic insights.

    If no AI endpoint is configured (the default, and the local-first
    guarantee), or the call fails for any reason, falls back to a short
    deterministic summary string built from the insights themselves -
    never raises, never blocks the dashboard.
    """
    insights = compute_insights(user_id, db_module)
    if not insights:
        return "No issues detected - keep logging your sessions and check back as patterns emerge."

    endpoint = app.config.get("AI_ENDPOINT")
    if endpoint:
        try:
            import requests

            from .export_ai import build_export

            resp = requests.post(
                endpoint,
                json={"insights": insights, "data": build_export(user_id, db_module)},
                timeout=5,
            )
            resp.raise_for_status()
            text = (resp.json() or {}).get("summary")
            if text:
                return text
        except Exception:
            pass  # graceful fallback below

    titles = "; ".join(i["title"].lower() for i in insights[:4])
    return f"Coach notes: {titles}."
