"""
Mandatory entry assessment after subject selection (up to 120 questions).
Questions are sampled from existing topic quizzes across enrolled subjects.
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user, load_users, save_users

DATA_DIR = Path(__file__).parent.parent / "data"
TOPICS_FILE = DATA_DIR / "topics.json"
QUIZ_FILE = DATA_DIR / "quiz_questions.json"
SESSION_DIR = DATA_DIR / "entry_quiz_sessions"

router = APIRouter()

MAX_QUESTIONS = 120


def _difficulty(qid: str) -> str:
    h = int(hashlib.md5(qid.encode()).hexdigest(), 16)
    return ["easy", "medium", "hard"][h % 3]


def _load_topics() -> list:
    with open(TOPICS_FILE) as f:
        return json.load(f)


def _load_quizzes() -> dict:
    with open(QUIZ_FILE) as f:
        return json.load(f)


def _build_pool(subject_ids: list[str]) -> list[dict]:
    topics = _load_topics()
    quizzes = _load_quizzes()
    pool = []
    for topic in topics:
        if topic["subject_id"] not in subject_ids:
            continue
        for qz_id in topic.get("quiz_ids") or []:
            quiz = quizzes.get(qz_id)
            if not quiz:
                continue
            for q in quiz["questions"]:
                pool.append({
                    **q,
                    "_topic_id": topic["id"],
                    "_topic_name": topic["name"],
                    "_subject_id": topic["subject_id"],
                    "_difficulty": _difficulty(q["id"]),
                })
    return pool


def _sample_pool(pool: list[dict], n: int) -> list[dict]:
    if len(pool) <= n:
        return list(pool)
    buckets = {"easy": [], "medium": [], "hard": []}
    for item in pool:
        buckets[item["_difficulty"]].append(item)
    for k in buckets:
        random.shuffle(buckets[k])
    per = n // 3
    rest = n % 3
    out = []
    for d in ("easy", "medium", "hard"):
        take = per + (1 if rest > 0 else 0)
        rest = max(0, rest - 1)
        out.extend(buckets[d][:take])
    # Fill if bucket short
    needed = n - len(out)
    if needed > 0:
        remainder = [p for p in pool if p not in out]
        random.shuffle(remainder)
        out.extend(remainder[:needed])
    random.shuffle(out)
    return out[:n]


def _session_path(user_id: str) -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return SESSION_DIR / f"{user_id}.json"


class EntrySubmit(BaseModel):
    answers: dict[str, int] = Field(default_factory=dict)
    time_taken_seconds: int | None = Field(default=None, ge=0)


@router.get("/entry-quiz/status")
def entry_status(current_user: dict = Depends(get_current_user)):
    return {
        "entry_quiz_completed": current_user.get("entry_quiz_completed", False),
        "skill_level": current_user.get("skill_level"),
        "selected_subjects": current_user.get("selected_subjects", []),
    }


@router.get("/entry-quiz/current")
def get_current_entry_session(current_user: dict = Depends(get_current_user)):
    """
    Return the in-progress entry assessment if a session file exists (resume without regenerating).
    """
    if current_user.get("entry_quiz_completed"):
        raise HTTPException(status_code=400, detail="Entry assessment already completed.")
    path = _session_path(current_user["id"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="No active entry assessment. Call /entry-quiz/start.")

    with open(path) as f:
        session = json.load(f)
    full = session["questions"]
    public = [
        {
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
            "topic_name": q.get("_topic_name", ""),
            "difficulty": q.get("_difficulty", ""),
        }
        for q in full
    ]
    return {
        "quiz_id": "entry_assessment",
        "total_questions": len(public),
        "questions": public,
        "resumed": True,
    }


@router.post("/entry-quiz/start")
def start_entry_quiz(current_user: dict = Depends(get_current_user)):
    subjects = current_user.get("selected_subjects", [])
    if not subjects:
        raise HTTPException(status_code=400, detail="Select at least one subject first.")
    if current_user.get("entry_quiz_completed"):
        raise HTTPException(status_code=400, detail="Entry assessment already completed.")

    pool = _build_pool(subjects)
    if not pool:
        raise HTTPException(status_code=404, detail="No questions available for selected subjects.")

    n = min(MAX_QUESTIONS, len(pool))
    selected = _sample_pool(pool, n)

    full = selected
    public = []
    for q in full:
        public.append({
            "id": q["id"],
            "question": q["question"],
            "options": q["options"],
            "topic_name": q["_topic_name"],
            "difficulty": q["_difficulty"],
        })

    with open(_session_path(current_user["id"]), "w") as f:
        json.dump({"questions": full, "created_at": datetime.utcnow().isoformat()}, f, indent=2)

    return {
        "quiz_id": "entry_assessment",
        "total_questions": len(public),
        "questions": public,
        "resumed": False,
    }


@router.post("/entry-quiz/submit")
def submit_entry_quiz(body: EntrySubmit, current_user: dict = Depends(get_current_user)):
    path = _session_path(current_user["id"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="No active entry quiz. Call /entry-quiz/start first.")

    with open(path) as f:
        session = json.load(f)
    questions = session["questions"]

    correct = 0
    for q in questions:
        if body.answers.get(q["id"]) == q["answer"]:
            correct += 1
    total = len(questions)
    score_pct = round((correct / total * 100), 1) if total else 0.0

    if score_pct < 50:
        level = "beginner"
    elif score_pct < 80:
        level = "intermediate"
    else:
        level = "advanced"

    users = load_users()
    for u in users:
        if u["id"] == current_user["id"]:
            u["entry_quiz_completed"] = True
            u["skill_level"] = level
            u["entry_quiz_result"] = {
                "score": correct,
                "total": total,
                "score_pct": score_pct,
                "skill_level": level,
                "time_taken_seconds": body.time_taken_seconds,
                "completed_at": datetime.utcnow().isoformat(),
            }
            break
    save_users(users)
    path.unlink(missing_ok=True)

    return {
        "score": correct,
        "total": total,
        "score_pct": score_pct,
        "skill_level": level,
        "message": f"Your level is set to {level}. Learning path and quizzes will adapt to this.",
    }
