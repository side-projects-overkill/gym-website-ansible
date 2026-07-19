"""Progressive-overload helpers for the workout plan.

Progressive overload just means: once you can comfortably hit the top of
your rep range for an exercise, add a little weight next time so the
muscle keeps adapting. This module has no state of its own - it reads
logged sets from `db.exercise_logs` and turns them into a plain-language
suggestion for the next session.
"""
import re

WEIGHT_INCREMENT_KG = 2.5


def parse_target_reps(sets_reps):
    """Best-effort extraction of the top of the rep range from a free-text
    "sets x reps" string like "3 x 8-12" or "4x10" -> 12 / 10.

    The workout YAML stores this as free text for human readability, so
    this is deliberately forgiving - it just grabs the last number in the
    string. Returns None if no number is found."""
    if not sets_reps:
        return None
    matches = re.findall(r"\d+", str(sets_reps))
    if not matches:
        return None
    return int(matches[-1])


def _fmt(value):
    return f"{value:g}"


def suggest_next(last_log, target_reps):
    """Returns a short suggestion string for the next time this exercise is
    performed, or None if there's no logged history to base one on.

    Heuristic: hit (or beat) the target rep count last time -> bump the
    weight by a small fixed increment. Otherwise, repeat the same weight
    and focus on adding reps before adding load.
    """
    if last_log is None or last_log["weight_kg"] is None:
        return None

    weight = last_log["weight_kg"]
    reps = last_log["reps"]

    if target_reps is not None and reps is not None and reps >= target_reps:
        return f"Add weight -> try {_fmt(weight + WEIGHT_INCREMENT_KG)}kg"
    return f"Repeat {_fmt(weight)}kg, aim for more reps"


def annotate_days(days, user_id, db_module):
    """Mutates `days` (as parsed from the workout YAML) in place, adding a
    `last_log` and `suggestion` key to every exercise dict so templates can
    render progressive-load info without any extra queries per row."""
    logs_by_name = db_module.latest_exercise_logs_by_name(user_id)
    for day in days:
        for ex in day.get("exercises", []) or []:
            last_log = logs_by_name.get(ex.get("name"))
            target_reps = parse_target_reps(ex.get("sets_reps"))
            ex["last_log"] = last_log
            ex["suggestion"] = suggest_next(last_log, target_reps)
    return days
