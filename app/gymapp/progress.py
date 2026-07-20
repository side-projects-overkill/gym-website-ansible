"""Best-effort heuristics that turn a user's attendance + weight history into
a friendly "are you on track" summary.

Pure logic module - no Flask Blueprint, no routes. Intended to be imported
and called by dashboard code (or anything else) once wired up:

    from gymapp import progress
    result = progress.compute_progress(user_id)

This is a heuristic feature, not a medical/scientific tool - it should
never raise, and always returns a well-formed dict (see `_fallback`).
"""
from datetime import timedelta

from . import db, localtime

WEIGHT_METRIC_KEY = "weight_kg"

ATTENDANCE_WINDOW_DAYS = 7
WEIGHT_LOOKBACK_DAYS = 14
WEIGHT_BASELINE_MAX_AGE_DAYS = 21
WEIGHT_FLAT_THRESHOLD_KG = 0.1


def _fallback():
    return {
        "status": "insufficient_data",
        "message": "Check in at the gym and log a few metrics to start tracking your progress.",
        "weight_signal": {
            "status": "insufficient_data",
            "detail": "Log your weight a few times to see a trend.",
        },
        "attendance_signal": {
            "status": "insufficient_data",
            "detail": "Check in at the gym to start tracking your attendance.",
            "visits_this_week": 0,
            "goal_weekly_visits": 0,
        },
    }


def _attendance_signal(user_id, user):
    goal_weekly_visits = user["goal_weekly_visits"] or 0
    since = (localtime.today() - timedelta(days=ATTENDANCE_WINDOW_DAYS - 1)).isoformat()
    visits_this_week = db.count_visits_since(user_id, since)

    if db.total_visit_count(user_id) == 0:
        return {
            "status": "insufficient_data",
            "detail": "Check in at the gym to start tracking your attendance.",
            "visits_this_week": visits_this_week,
            "goal_weekly_visits": goal_weekly_visits,
        }

    if goal_weekly_visits <= 0:
        # No meaningful goal set - just report the raw number, on_track by default.
        return {
            "status": "on_track",
            "detail": f"You've been to the gym {visits_this_week} time(s) this week.",
            "visits_this_week": visits_this_week,
            "goal_weekly_visits": goal_weekly_visits,
        }

    if visits_this_week >= goal_weekly_visits:
        return {
            "status": "on_track",
            "detail": (
                f"You've been to the gym {visits_this_week}/{goal_weekly_visits} "
                "times this week - right on target."
            ),
            "visits_this_week": visits_this_week,
            "goal_weekly_visits": goal_weekly_visits,
        }

    if visits_this_week >= goal_weekly_visits * 0.5:
        return {
            "status": "off_track",
            "detail": (
                f"You're at {visits_this_week}/{goal_weekly_visits} visits this week - "
                "a bit behind pace."
            ),
            "visits_this_week": visits_this_week,
            "goal_weekly_visits": goal_weekly_visits,
        }

    return {
        "status": "off_track",
        "detail": f"You've only made it {visits_this_week}/{goal_weekly_visits} times this week.",
        "visits_this_week": visits_this_week,
        "goal_weekly_visits": goal_weekly_visits,
    }


def _pick_weight_baseline(rows):
    """`rows` is ascending by log_date. Pick the oldest point within the
    last WEIGHT_BASELINE_MAX_AGE_DAYS days as the comparison baseline; if
    none exists that recent, fall back to the very first historical point."""
    cutoff = (localtime.today() - timedelta(days=WEIGHT_BASELINE_MAX_AGE_DAYS)).isoformat()
    for row in rows:
        if row["log_date"] >= cutoff:
            return row
    return rows[0]


def _weight_signal(user_id, user):
    goal_type = user["goal_type"]

    if goal_type == "maintain":
        return {
            "status": "neutral",
            "detail": "You're on a maintenance goal - keep your weight steady.",
        }

    rows = db.metric_history(user_id, WEIGHT_METRIC_KEY, limit=100)
    if len(rows) < 2:
        return {
            "status": "insufficient_data",
            "detail": "Log your weight a few times to see a trend.",
        }

    latest = rows[-1]["value"]
    baseline = _pick_weight_baseline(rows)["value"]
    delta = latest - baseline

    if goal_type == "lose":
        if delta <= -WEIGHT_FLAT_THRESHOLD_KG:
            return {
                "status": "on_track",
                "detail": (
                    f"You're down {abs(delta):.1f} kg over the period - great progress "
                    "toward your goal."
                ),
            }
        if delta > WEIGHT_FLAT_THRESHOLD_KG:
            return {
                "status": "off_track",
                "detail": f"You've gained {delta:.1f} kg, which is moving away from your goal.",
            }
        return {
            "status": "off_track",
            "detail": "Your weight has been flat - consider adjusting your routine to keep losing.",
        }

    if goal_type == "gain":
        if delta >= WEIGHT_FLAT_THRESHOLD_KG:
            return {
                "status": "on_track",
                "detail": (
                    f"You're up {delta:.1f} kg over the period - great progress toward "
                    "your goal."
                ),
            }
        if delta < -WEIGHT_FLAT_THRESHOLD_KG:
            return {
                "status": "off_track",
                "detail": (
                    f"You've lost {abs(delta):.1f} kg, which is moving away from your goal."
                ),
            }
        return {
            "status": "off_track",
            "detail": "Your weight has been flat - consider adjusting your routine to keep gaining.",
        }

    # Unknown goal_type value - treat like maintain rather than crash.
    return {
        "status": "neutral",
        "detail": "Set a goal type to get weight-trend feedback.",
    }


def _combine(weight_signal, attendance_signal):
    w_status = weight_signal["status"]
    a_status = attendance_signal["status"]

    # Weight is not a meaningful signal right now (maintain goal, or no
    # goal-type-specific feedback available) - let attendance drive things.
    if w_status in ("neutral",):
        if a_status == "insufficient_data":
            return "insufficient_data", "Check in at the gym to start tracking your progress."
        if a_status == "on_track":
            return "on_track", "Attendance is on track. " + attendance_signal["detail"]
        return "off_track", "Attendance needs attention. " + attendance_signal["detail"]

    if w_status == "insufficient_data" and a_status == "insufficient_data":
        return "insufficient_data", "Check in at the gym and log your weight to start tracking progress."

    if w_status == "insufficient_data":
        if a_status == "on_track":
            return "insufficient_data", "Attendance is on track. Log your weight a bit more to see a full picture."
        return "insufficient_data", "Log your weight a bit more, and try to get to the gym more often too."

    if a_status == "insufficient_data":
        if w_status == "on_track":
            return "insufficient_data", "Your weight trend looks good. Check in more often to track attendance too."
        return "insufficient_data", "Check in at the gym to start tracking your attendance."

    if w_status == "on_track" and a_status == "on_track":
        return "on_track", "You're on track with both attendance and your weight goal - keep it up!"

    if w_status == "off_track" and a_status == "off_track":
        return "off_track", "Both your attendance and weight trend need attention right now."

    # Mixed: one on_track, one off_track.
    if w_status == "off_track":
        return "mixed", "Attendance is on track, but your weight trend needs attention."
    return "mixed", "Your weight trend looks good, but attendance needs attention."


def compute_progress(user_id):
    """Returns a dict describing overall progress plus the two underlying
    signals (attendance, weight). Never raises - falls back to an
    insufficient_data payload on any unexpected error."""
    try:
        user = db.get_user(user_id)
        if user is None:
            return _fallback()

        attendance_signal = _attendance_signal(user_id, user)
        weight_signal = _weight_signal(user_id, user)
        status, message = _combine(weight_signal, attendance_signal)

        return {
            "status": status,
            "message": message,
            "weight_signal": weight_signal,
            "attendance_signal": attendance_signal,
        }
    except Exception:
        return _fallback()
