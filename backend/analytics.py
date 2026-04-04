"""
analytics.py — Aggregates all data for the Dashboard and Performance pages.
This is what powers the main student dashboard view.
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends

from backend.auth import get_current_user
from utils.progress_calculator import calculate_topic_progress, calculate_subject_progress
from utils.weak_area_detector import (
    detect_weak_topics,
    topic_mastery_report,
    strength_distribution,
)

DATA_DIR = Path(__file__).parent.parent / "data"
SUBJECTS_FILE = DATA_DIR / "subjects.json"
TOPICS_FILE = DATA_DIR / "topics.json"
ATTEMPTS_FILE = DATA_DIR / "quiz_attempts.json"

router = APIRouter()


def load_json(path):
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


@router.get("/dashboard")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    """
    Return everything the dashboard needs in a single API call:
      - Enrolled subjects with progress
      - Per-topic breakdown
      - Weak topics list
      - Recent quiz attempts
      - Summary stats
    """
    subjects_data = load_json(SUBJECTS_FILE)
    topics_data = load_json(TOPICS_FILE)
    enrolled_ids = current_user.get("selected_subjects", [])

    if not isinstance(subjects_data, list):
        subjects_data = []
    if not isinstance(topics_data, list):
        topics_data = []

    subject_map = {s["id"]: s for s in subjects_data}

    # ── Subject Progress ───────────────────────────────────────────────────────
    subject_progress = []
    for sid in enrolled_ids:
        sp = calculate_subject_progress(current_user["id"], sid)
        subject_info = subject_map.get(sid, {})
        subject_progress.append({
            "subject_id": sid,
            "subject_name": subject_info.get("name", sid),
            "description": subject_info.get("description", ""),
            "overall_progress_pct": sp["overall_progress_pct"],
            "topics": sp["topics"],
        })

    # ── Weak Topics ────────────────────────────────────────────────────────────
    weak_topics = detect_weak_topics(current_user["id"], enrolled_ids)

    # ── Recent Quiz Attempts ───────────────────────────────────────────────────
    attempts_data = load_json(ATTEMPTS_FILE)
    user_attempts = attempts_data.get(current_user["id"], {})

    # Sort by recency using raw attempts list timestamps (not exposed to client)
    _with_sort = []
    for topic_id, attempts in user_attempts.items():
        for attempt in attempts:
            _with_sort.append((attempt.get("submitted_at", ""), topic_id, attempt))
    _with_sort.sort(key=lambda x: x[0], reverse=True)
    seen = set()
    ordered = []
    for _, topic_id, attempt in _with_sort:
        k = (topic_id, attempt.get("attempt_id"))
        if k in seen:
            continue
        seen.add(k)
        topic_info = next((t for t in topics_data if t["id"] == topic_id), {})
        ordered.append({
            "topic_id": topic_id,
            "topic_name": topic_info.get("name", topic_id),
            "quiz_id": attempt.get("quiz_id"),
            "score": attempt.get("score"),
            "total": attempt.get("total"),
            "score_pct": attempt.get("score_pct"),
            "time_taken_seconds": attempt.get("time_taken_seconds"),
        })
        if len(ordered) >= 10:
            break
    recent_attempts = ordered

    mastery_rows = topic_mastery_report(current_user["id"], enrolled_ids)
    strength_dist = strength_distribution(mastery_rows)

    # ── Summary Stats ──────────────────────────────────────────────────────────
    all_topic_pcts = [
        calculate_topic_progress(current_user["id"], t["id"])["overall_progress_pct"]
        for t in topics_data
        if t["subject_id"] in enrolled_ids
    ]
    overall_avg = (
        round(sum(all_topic_pcts) / len(all_topic_pcts), 1)
        if all_topic_pcts else 0.0
    )

    # Count topics by status
    topics_complete = sum(1 for p in all_topic_pcts if p >= 80)
    topics_in_progress = sum(1 for p in all_topic_pcts if 0 < p < 80)
    topics_not_started = sum(1 for p in all_topic_pcts if p == 0)

    profile = current_user.get("profile") or {}
    return {
        "user": {
            "id": current_user["id"],
            "username": current_user["username"],
            "full_name": current_user["full_name"],
            "onboarding_complete": profile.get("onboarding_complete", False),
            "entry_quiz_completed": current_user.get("entry_quiz_completed", False),
            "skill_level": current_user.get("skill_level"),
        },
        "summary": {
            "overall_progress_pct": overall_avg,
            "enrolled_subjects": len(enrolled_ids),
            "topics_complete": topics_complete,
            "topics_in_progress": topics_in_progress,
            "topics_not_started": topics_not_started,
            "weak_topic_count": len(weak_topics),
        },
        "charts": {
            "strength_pie": [
                {"label": "Weak (<30%)", "count": strength_dist.get("weak", 0)},
                {"label": "Average (30–65%)", "count": strength_dist.get("average", 0)},
                {"label": "Strong (≥65%)", "count": strength_dist.get("strong", 0)},
            ],
        },
        "subject_progress": subject_progress,
        "weak_topics": weak_topics,
        "weak_area_report": mastery_rows,
        "recent_quiz_attempts": recent_attempts,
    }


@router.get("/performance")
def get_performance(current_user: dict = Depends(get_current_user)):
    """
    Detailed performance breakdown for charts and analytics.
    Returns topic-level data suitable for Recharts / Chart.js.
    """
    enrolled_ids = current_user.get("selected_subjects", [])
    topics_data = load_json(TOPICS_FILE)
    if not isinstance(topics_data, list):
        topics_data = []

    enrolled_topics = [t for t in topics_data if t["subject_id"] in enrolled_ids]

    attempts_data = load_json(ATTEMPTS_FILE)
    user_attempts = attempts_data.get(current_user["id"], {})

    def _avg_time(topic_id: str):
        attempts = user_attempts.get(topic_id, [])
        times = [a.get("time_taken_seconds") for a in attempts if a.get("time_taken_seconds") is not None]
        if not times:
            return None
        return round(sum(times) / len(times), 1)

    # Build chart-ready data
    chart_data = []
    for topic in enrolled_topics:
        tp = calculate_topic_progress(current_user["id"], topic["id"])
        chart_data.append({
            "topic_id": topic["id"],
            "topic_name": topic["name"],
            "subject_id": topic["subject_id"],
            "resource_completion_pct": tp["resource_completion_pct"],
            "avg_quiz_score": tp["avg_quiz_score"],
            "overall_progress_pct": tp["overall_progress_pct"],
            "quiz_attempts": tp["quiz_attempts_count"],
            "best_quiz_score": tp["best_quiz_score"],
            "avg_time_seconds": _avg_time(topic["id"]),
        })

    mastery_rows = topic_mastery_report(current_user["id"], enrolled_ids)
    strength_dist = strength_distribution(mastery_rows)

    return {
        "chart_data": chart_data,
        "total_topics": len(enrolled_topics),
        "strength_distribution": strength_dist,
    }
