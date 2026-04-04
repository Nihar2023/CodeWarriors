"""
subjects.py — Manages subjects and topic browsing.
Allows users to enroll/unenroll in subjects and view topic lists.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.auth import get_current_user, load_users, save_users
from utils.user_defaults import ensure_user_defaults
from utils.progress_calculator import calculate_topic_progress

DATA_DIR = Path(__file__).parent.parent / "data"
SUBJECTS_FILE = DATA_DIR / "subjects.json"
TOPICS_FILE = DATA_DIR / "topics.json"

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────
def load_subjects() -> list:
    with open(SUBJECTS_FILE, "r") as f:
        return json.load(f)


def load_topics() -> list:
    with open(TOPICS_FILE, "r") as f:
        return json.load(f)


# ── Pydantic Models ────────────────────────────────────────────────────────────
class SubjectSelectionRequest(BaseModel):
    subject_ids: list[str]   # List of subject IDs the user wants to enroll in


# ── Routes ─────────────────────────────────────────────────────────────────────
@router.get("/subjects")
def get_all_subjects(current_user: dict = Depends(get_current_user)):
    """
    Return all available subjects.
    Each subject is annotated with whether the user is enrolled.
    """
    subjects = load_subjects()
    enrolled = set(current_user.get("selected_subjects", []))

    return [
        {**s, "enrolled": s["id"] in enrolled}
        for s in subjects
    ]


@router.post("/select-subjects")
def select_subjects(req: SubjectSelectionRequest, current_user: dict = Depends(get_current_user)):
    """
    Set (replace) the user's enrolled subjects.
    Called during onboarding and whenever user updates their subjects.
    """
    subjects = load_subjects()
    valid_ids = {s["id"] for s in subjects}

    # Validate all submitted IDs exist
    invalid = [sid for sid in req.subject_ids if sid not in valid_ids]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown subject IDs: {invalid}")

    # Update user record
    users = load_users()
    requires_entry = False
    for u in users:
        if u["id"] == current_user["id"]:
            u["selected_subjects"] = req.subject_ids
            ensure_user_defaults(u)
            requires_entry = bool(req.subject_ids) and not u.get("entry_quiz_completed", False)
            break
    save_users(users)

    return {
        "message": "Subjects updated successfully.",
        "selected_subjects": req.subject_ids,
        "requires_entry_quiz": requires_entry,
    }


@router.post("/enroll/{subject_id}")
def enroll_subject(subject_id: str, current_user: dict = Depends(get_current_user)):
    """Enroll in a single subject without disturbing other enrollments."""
    subjects = load_subjects()
    valid_ids = {s["id"] for s in subjects}

    if subject_id not in valid_ids:
        raise HTTPException(status_code=404, detail="Subject not found.")

    users = load_users()
    requires_entry = False
    enrolled_list: list = []
    for u in users:
        if u["id"] == current_user["id"]:
            enrolled = set(u.get("selected_subjects", []))
            enrolled.add(subject_id)
            u["selected_subjects"] = list(enrolled)
            enrolled_list = u["selected_subjects"]
            ensure_user_defaults(u)
            requires_entry = bool(u["selected_subjects"]) and not u.get("entry_quiz_completed", False)
            break
    save_users(users)
    return {
        "message": f"Enrolled in {subject_id}.",
        "selected_subjects": enrolled_list,
        "requires_entry_quiz": requires_entry,
    }


@router.post("/unenroll/{subject_id}")
def unenroll_subject(subject_id: str, current_user: dict = Depends(get_current_user)):
    """Remove a subject from the user's enrollments."""
    users = load_users()
    for u in users:
        if u["id"] == current_user["id"]:
            enrolled = set(u.get("selected_subjects", []))
            enrolled.discard(subject_id)
            u["selected_subjects"] = list(enrolled)
            break
    save_users(users)
    return {"message": f"Unenrolled from {subject_id}.", "selected_subjects": list(enrolled)}


@router.get("/topics")
def get_topics(subject_id: str = None, current_user: dict = Depends(get_current_user)):
    """
    Return topics.
    - If subject_id is provided: return topics for that subject only
    - Otherwise: return all topics for the user's enrolled subjects
    """
    topics = load_topics()
    enrolled = current_user.get("selected_subjects", [])

    if subject_id:
        # Filter by specific subject
        result = [t for t in topics if t["subject_id"] == subject_id]
    else:
        # Return topics for all enrolled subjects
        result = [t for t in topics if t["subject_id"] in enrolled]

    return result


@router.get("/topics-with-progress")
def get_topics_with_progress(subject_id: str | None = None, current_user: dict = Depends(get_current_user)):
    """Topics with blended completion % and subject display name (for learning UI)."""
    topics = load_topics()
    enrolled = current_user.get("selected_subjects", [])
    subjects = load_subjects()
    subject_map = {s["id"]: s for s in subjects}

    if subject_id:
        filtered = [t for t in topics if t["subject_id"] == subject_id]
    else:
        filtered = [t for t in topics if t["subject_id"] in enrolled]

    out = []
    for t in filtered:
        tp = calculate_topic_progress(current_user["id"], t["id"])
        subj = subject_map.get(t["subject_id"], {})
        sname = subj.get("name", t["subject_id"])
        desc = t.get("description") or ""
        out.append({
            "id": t["id"],
            "subject_id": t["subject_id"],
            "subject_name": sname,
            "name": t["name"],
            "description": desc,
            "completion_pct": tp["overall_progress_pct"],
            "search_blob": f"{t['name']} {desc} {sname}".lower(),
        })
    return out


@router.get("/topics/{topic_id}")
def get_topic_detail(topic_id: str, current_user: dict = Depends(get_current_user)):
    """Return a single topic's full detail."""
    topics = load_topics()
    topic = next((t for t in topics if t["id"] == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found.")
    return topic
