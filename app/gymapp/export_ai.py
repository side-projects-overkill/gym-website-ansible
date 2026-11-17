"""AI-readable progress export (Feature A).

Builds a compact, token-efficient snapshot of a member's training data -
one function assembles the payload from existing DB reads, then two pure
formatters render it as Markdown (for pasting straight into any LLM chat,
with a pre-baked system-prompt wrapper) or JSON (for API use).

No new dependencies, no schema changes: everything is derived from the
existing tables via the same `db` module the rest of the app uses.
"""
from datetime import timedelta
import json

from . import localtime

FORMAT_VERSION = 1

SYSTEM_PROMPT = (
    "You are an experienced strength and conditioning coach. Below is a "
    "member's recent training and body-metric data, exported from their "
    "gym tracker. Analyse the trends, identify plateaus or progress, and "
    "give 3-5 specific, actionable recommendations for the next 1-2 weeks. "
    "Be concise and practical; cite the numbers you base each point on."
)


def build_export(user_id, db_module, days=90):
    """Assemble the export payload for the last `days` days of data."""
    today = localtime.today()
    since = (today - timedelta(days=days)).isoformat()
    user = db_module.get_user(user_id)

    # Body metrics: latest value per metric (label/unit resolved).
    body_metrics = [
        {
            "metric": row["metric_key"],
            "label": row["label"],
            "unit": row["unit"],
            "latest_value": row["value"],
            "as_of": row["log_date"],
        }
        for row in db_module.latest_value_per_metric(user_id)
        if row["value"] is not None
    ]

    # Exercise history within the window, newest session first per exercise.
    cutoff = (today - timedelta(days=days)).isoformat()
    all_rows = db_module.get_db().execute(
        "SELECT exercise_name, log_date, weight_kg, reps, sets "
        "FROM exercise_logs WHERE user_id = ? AND log_date >= ? "
        "ORDER BY exercise_name, log_date ASC, id ASC",
        (user_id, cutoff),
    ).fetchall()
    by_name = {}
    for row in all_rows:
        by_name.setdefault(row["exercise_name"], []).append(
            {
                "date": row["log_date"],
                "weight_kg": row["weight_kg"],
                "reps": row["reps"],
                "sets": row["sets"],
            }
        )
    exercises = [
        {"name": name, "sessions": sessions[::-1]}
        for name, sessions in sorted(by_name.items())
    ]

    visits = db_module.count_visits_since(user_id, since)
    walks = db_module.count_walks_since(user_id, since)

    return {
        "format_version": FORMAT_VERSION,
        "generated_at": localtime.today().isoformat(),
        "range_days": days,
        "goals": {
            "goal_type": user["goal_type"],
            "goal_target_weight": user["goal_target_weight"],
            "goal_weekly_visits": user["goal_weekly_visits"],
            "goal_weekly_walks": user["goal_weekly_walks"],
        },
        "body_metrics": body_metrics,
        "exercises": exercises,
        "activity": {
            "visits": visits,
            "walks": walks,
        },
    }


def to_json(payload):
    return json.dumps(payload, indent=2, sort_keys=False)


def to_markdown(payload):
    """Render the payload as a compact, LLM-ready Markdown report."""
    lines = []
    lines.append("# Gym Progress Report")
    lines.append("")
    lines.append(f"> {SYSTEM_PROMPT}")
    lines.append("")
    lines.append(
        f"Data window: last {payload['range_days']} days "
        f"(generated {payload['generated_at']})."
    )

    lines.append("")
    lines.append("## Goals")
    g = payload["goals"]
    lines.append(
        f"- Goal: {g['goal_type']}"
        + (f", target weight {g['goal_target_weight']}kg" if g["goal_target_weight"] else "")
        + f"; {g['goal_weekly_visits']} gym visits and "
        f"{g['goal_weekly_walks']} walks per week"
    )

    lines.append("")
    lines.append("## Body Metrics")
    if payload["body_metrics"]:
        lines.append("| Metric | Latest | Date |")
        lines.append("|---|---|---|")
        for m in payload["body_metrics"]:
            lines.append(
                f"| {m['label']} | {m['latest_value']:g} {m['unit']} | {m['as_of']} |"
            )
    else:
        lines.append("No body metrics logged.")

    lines.append("")
    lines.append("## Exercise History")
    if payload["exercises"]:
        for ex in payload["exercises"]:
            lines.append("")
            lines.append(f"**{ex['name']}**")
            lines.append("| Date | Weight | Reps | Sets |")
            lines.append("|---|---|---|---|")
            for s in ex["sessions"]:
                w = f"{s['weight_kg']:g}" if s["weight_kg"] is not None else "-"
                r = s["reps"] if s["reps"] is not None else "-"
                st = s["sets"] if s["sets"] is not None else "-"
                lines.append(f"| {s['date']} | {w} | {r} | {st} |")
    else:
        lines.append("No exercise history in this window.")

    lines.append("")
    lines.append("## Activity")
    a = payload["activity"]
    lines.append(f"- Gym visits: {a['visits']}")
    lines.append(f"- Walks: {a['walks']}")

    lines.append("")
    return "\n".join(lines)
