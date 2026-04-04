"""
utils/weak_area_detector.py — Topic strength and weak-area detection.

Strength bands (overall progress / blended metric):
  - Weak:   < 30%
  - Average: 30% – 65% (exclusive of 65% for "Strong" start per spec: 65%+ → Strong)
  - Strong: >= 65%

Legacy weak-topic alerts (dashboard "needs attention"):
  - Overall progress < 30% OR latest quiz <= 40% when attempted
"""

from utils.progress_calculator import calculate_topic_progress
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TOPICS_FILE = DATA_DIR / "topics.json"
SUBJECTS_FILE = DATA_DIR / "subjects.json"


def strength_category(overall_progress_pct: float) -> str:
    if overall_progress_pct < 30:
        return "weak"
    if overall_progress_pct < 65:
        return "average"
    return "strong"


def load_json(path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def detect_weak_topics(user_id: str, subject_ids: list[str]) -> list[dict]:
    """
    Scan all topics in the user's enrolled subjects and flag weak ones.

    Returns a list of weak topic dicts, each with:
      - topic info
      - progress metrics
      - reason string explaining why it's flagged as weak
    """
    topics = load_json(TOPICS_FILE)
    subjects = load_json(SUBJECTS_FILE)

    # Build subject id -> name lookup
    subject_map = {s["id"]: s["name"] for s in subjects}

    weak_topics = []

    for topic in topics:
        # Only evaluate topics in the user's enrolled subjects
        if topic["subject_id"] not in subject_ids:
            continue

        tp = calculate_topic_progress(user_id, topic["id"])

        reasons = []

        # Rule 1: Overall progress is very low
        if tp["overall_progress_pct"] < 30:
            reasons.append(f"Overall progress is only {tp['overall_progress_pct']}% (threshold: 30%)")

        # Rule 2: Quiz was attempted but score is poor
        if tp["has_quiz_attempt"] and tp["latest_quiz_score"] is not None:
            if tp["latest_quiz_score"] <= 40:
                reasons.append(
                    f"Latest quiz score is {tp['latest_quiz_score']}% (threshold: 40%)"
                )

        if reasons:
            weak_topics.append({
                "topic_id": topic["id"],
                "topic_name": topic["name"],
                "subject_id": topic["subject_id"],
                "subject_name": subject_map.get(topic["subject_id"], topic["subject_id"]),
                "overall_progress_pct": tp["overall_progress_pct"],
                "latest_quiz_score": tp["latest_quiz_score"],
                "resource_completion_pct": tp["resource_completion_pct"],
                "reasons": reasons,
            })

    # Sort: weakest first (lowest overall progress)
    weak_topics.sort(key=lambda t: t["overall_progress_pct"])
    return weak_topics


def topic_mastery_report(user_id: str, subject_ids: list[str]) -> list[dict]:
    """Per-topic row for dashboards: progress + strength category."""
    topics = load_json(TOPICS_FILE)
    subjects = load_json(SUBJECTS_FILE)
    subject_map = {s["id"]: s["name"] for s in subjects}

    rows = []
    for topic in topics:
        if topic["subject_id"] not in subject_ids:
            continue
        tp = calculate_topic_progress(user_id, topic["id"])
        cat = strength_category(tp["overall_progress_pct"])
        rows.append({
            "topic_id": topic["id"],
            "topic_name": topic["name"],
            "subject_id": topic["subject_id"],
            "subject_name": subject_map.get(topic["subject_id"], topic["subject_id"]),
            "overall_progress_pct": tp["overall_progress_pct"],
            "resource_completion_pct": tp["resource_completion_pct"],
            "avg_quiz_score": tp["avg_quiz_score"],
            "latest_quiz_score": tp["latest_quiz_score"],
            "strength_category": cat,
        })
    rows.sort(key=lambda r: r["overall_progress_pct"])
    return rows


def strength_distribution(rows: list[dict]) -> dict[str, int]:
    dist = {"weak": 0, "average": 0, "strong": 0}
    for r in rows:
        dist[r["strength_category"]] = dist.get(r["strength_category"], 0) + 1
    return dist
