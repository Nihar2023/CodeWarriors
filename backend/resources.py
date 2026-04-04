"""
resources.py — Serves learning resources for each topic and tracks completion.
Resource completion is stored in progress.json under each user's record.
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.auth import get_current_user
from utils.progress_calculator import calculate_topic_progress
from utils.quiz_ai import personalized_resource_intro
from utils.weak_area_detector import detect_weak_topics

DATA_DIR = Path(__file__).parent.parent / "data"
TOPICS_FILE = DATA_DIR / "topics.json"
RESOURCES_FILE = DATA_DIR / "resources.json"
PROGRESS_FILE = DATA_DIR / "progress.json"

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_resources() -> list:
    with open(RESOURCES_FILE, "r") as f:
        return json.load(f)


def load_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {}
    with open(PROGRESS_FILE, "r") as f:
        return json.load(f)


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── Pydantic Models ────────────────────────────────────────────────────────────
class MarkCompleteRequest(BaseModel):
    resource_id: str
    topic_id: str


# ── Routes ─────────────────────────────────────────────────────────────────────
@router.get("/resources")
async def get_resources(topic_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return resources for a topic with completion flags and optional AI personalization blurbs.
    """
    resources = load_resources()
    progress = load_progress()

    user_progress = progress.get(current_user["id"], {})
    topic_progress = user_progress.get("topics", {}).get(topic_id, {})
    completed_resources = set(topic_progress.get("completed_resources", []))

    topic_resources = [
        {**r, "completed": r["id"] in completed_resources}
        for r in resources
        if r["topic_id"] == topic_id
    ]

    if not topic_resources:
        raise HTTPException(status_code=404, detail="No resources found for this topic.")

    topic_name = topic_id
    if TOPICS_FILE.exists():
        with open(TOPICS_FILE) as f:
            topics = json.load(f)
        for t in topics:
            if t["id"] == topic_id:
                topic_name = t.get("name", topic_id)
                break

    tp = calculate_topic_progress(current_user["id"], topic_id)
    weak = detect_weak_topics(current_user["id"], current_user.get("selected_subjects", []))
    weak_hint = "; ".join(f"{w['topic_name']}" for w in weak[:4]) or "Balanced progress"

    for r in topic_resources:
        note = await personalized_resource_intro(
            full_name=current_user.get("full_name", "Student"),
            topic_name=topic_name,
            resource_title=r.get("title", ""),
            resource_type=r.get("type", "resource"),
            user_progress_pct=tp["overall_progress_pct"],
            weak_hint=weak_hint,
        )
        r["personalized_note"] = note

    return topic_resources


@router.post("/mark-resource-complete")
def mark_resource_complete(req: MarkCompleteRequest, current_user: dict = Depends(get_current_user)):
    """
    Toggle a resource as completed for the current user.
    Updates the completion list in progress.json and recalculates topic progress.
    """
    # Validate resource exists
    resources = load_resources()
    resource = next((r for r in resources if r["id"] == req.resource_id), None)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found.")

    progress = load_progress()
    uid = current_user["id"]

    # Initialise nested structure if first time for this user
    if uid not in progress:
        progress[uid] = {"topics": {}}
    if "topics" not in progress[uid]:
        progress[uid]["topics"] = {}
    if req.topic_id not in progress[uid]["topics"]:
        progress[uid]["topics"][req.topic_id] = {
            "completed_resources": [],
            "resource_completion_pct": 0.0,
        }

    topic_progress = progress[uid]["topics"][req.topic_id]
    completed = set(topic_progress.get("completed_resources", []))

    # Toggle: mark complete if not done, unmark if already done
    if req.resource_id in completed:
        completed.discard(req.resource_id)
        action = "unmarked"
    else:
        completed.add(req.resource_id)
        action = "marked"

    topic_progress["completed_resources"] = list(completed)

    # Recalculate resource completion percentage for this topic
    total_topic_resources = [r for r in resources if r["topic_id"] == req.topic_id]
    total = len(total_topic_resources)
    pct = round((len(completed) / total * 100), 1) if total > 0 else 0.0
    topic_progress["resource_completion_pct"] = pct
    topic_progress["last_updated"] = datetime.utcnow().isoformat()

    save_progress(progress)

    return {
        "message": f"Resource {action} as complete.",
        "resource_id": req.resource_id,
        "completed_resources": list(completed),
        "resource_completion_pct": pct,
    }


@router.get("/resources/progress/{topic_id}")
def get_topic_resource_progress(topic_id: str, current_user: dict = Depends(get_current_user)):
    """Return just the resource completion summary for a specific topic."""
    progress = load_progress()
    topic_progress = (
        progress.get(current_user["id"], {})
               .get("topics", {})
               .get(topic_id, {})
    )
    return {
        "topic_id": topic_id,
        "completed_resources": topic_progress.get("completed_resources", []),
        "resource_completion_pct": topic_progress.get("resource_completion_pct", 0.0),
    }
