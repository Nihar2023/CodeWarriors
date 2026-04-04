"""
utils/progress_calculator.py — Core logic for computing per-topic and overall subject progress.

Formula:
  - If quiz has been attempted:  Overall = 60% × resource_completion + 40% × avg_quiz_score
  - If no quiz attempted yet:    Overall = 100% × resource_completion
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TOPICS_FILE = DATA_DIR / "topics.json"
RESOURCES_FILE = DATA_DIR / "resources.json"
PROGRESS_FILE = DATA_DIR / "progress.json"
ATTEMPTS_FILE = DATA_DIR / "quiz_attempts.json"


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {} if path.suffix == ".json" and "progress" in path.name else []
    with open(path, "r") as f:
        return json.load(f)


def calculate_topic_progress(user_id: str, topic_id: str) -> dict:
    """
    Compute progress for a single topic for a given user.
    Returns a dict with all progress metrics.
    """
    progress_data = load_json(PROGRESS_FILE)
    resources = load_json(RESOURCES_FILE)

    user_progress = progress_data.get(user_id, {})
    topic_progress = user_progress.get("topics", {}).get(topic_id, {})

    # ── Resource Completion ────────────────────────────────────────────────────
    topic_resources = [r for r in resources if r["topic_id"] == topic_id]
    total_resources = len(topic_resources)
    completed_resources = topic_progress.get("completed_resources", [])
    resource_pct = round(
        (len(completed_resources) / total_resources * 100), 1
    ) if total_resources > 0 else 0.0

    # ── Quiz Score ─────────────────────────────────────────────────────────────
    quiz_scores = topic_progress.get("quiz_scores", [])
    has_quiz_attempt = len(quiz_scores) > 0
    avg_quiz_score = round(sum(quiz_scores) / len(quiz_scores), 1) if has_quiz_attempt else 0.0
    latest_quiz_score = topic_progress.get("latest_quiz_score", None)
    best_quiz_score = topic_progress.get("best_quiz_score", None)

    # ── Overall Progress (weighted formula) ────────────────────────────────────
    if has_quiz_attempt:
        # Both components count: resources 60%, quiz 40%
        overall_pct = round(0.6 * resource_pct + 0.4 * avg_quiz_score, 1)
    else:
        # No quiz attempted yet: resources carry 100% of the weight
        overall_pct = resource_pct

    return {
        "topic_id": topic_id,
        "resource_completion_pct": resource_pct,
        "completed_resources": completed_resources,
        "total_resources": total_resources,
        "has_quiz_attempt": has_quiz_attempt,
        "avg_quiz_score": avg_quiz_score,
        "latest_quiz_score": latest_quiz_score,
        "best_quiz_score": best_quiz_score,
        "quiz_attempts_count": len(quiz_scores),
        "overall_progress_pct": overall_pct,
    }


def calculate_subject_progress(user_id: str, subject_id: str) -> dict:
    """
    Compute overall progress for all topics within a subject.
    Subject progress = average of all its topic overall percentages.
    """
    topics = load_json(TOPICS_FILE)
    subject_topics = [t for t in topics if t["subject_id"] == subject_id]

    if not subject_topics:
        return {"subject_id": subject_id, "overall_progress_pct": 0.0, "topics": []}

    topic_progresses = [
        calculate_topic_progress(user_id, t["id"])
        for t in subject_topics
    ]

    subject_overall = round(
        sum(tp["overall_progress_pct"] for tp in topic_progresses) / len(topic_progresses), 1
    )

    return {
        "subject_id": subject_id,
        "overall_progress_pct": subject_overall,
        "topics": topic_progresses,
    }
