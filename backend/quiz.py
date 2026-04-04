"""
quiz.py — Quizzes, optional Gemini-personalized extensions, submissions with timing.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from utils.quiz_ai import build_extra_questions_for_topic, personalized_quiz_result_message
from utils.weak_area_detector import detect_weak_topics

DATA_DIR = Path(__file__).parent.parent / "data"
QUIZ_FILE = DATA_DIR / "quiz_questions.json"
ATTEMPTS_FILE = DATA_DIR / "quiz_attempts.json"
PROGRESS_FILE = DATA_DIR / "progress.json"
PERSONALIZED_DIR = DATA_DIR / "personalized_quizzes"
PERSONAL_PREFIX = "personalized__"

router = APIRouter()


def load_quizzes() -> dict:
    with open(QUIZ_FILE, "r") as f:
        return json.load(f)


def load_attempts() -> dict:
    if not ATTEMPTS_FILE.exists():
        return {}
    with open(ATTEMPTS_FILE, "r") as f:
        return json.load(f)


def save_attempts(attempts: dict) -> None:
    with open(ATTEMPTS_FILE, "w") as f:
        json.dump(attempts, f, indent=2)


def load_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {}
    with open(PROGRESS_FILE, "r") as f:
        return json.load(f)


def save_progress(progress: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def _save_personalized_bank(user_id: str, topic_id: str, questions: list) -> None:
    PERSONALIZED_DIR.mkdir(parents=True, exist_ok=True)
    path = PERSONALIZED_DIR / f"{user_id}_{topic_id}.json"
    payload = {"topic_id": topic_id, "questions": questions, "saved_at": datetime.utcnow().isoformat()}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def _load_personalized_bank(user_id: str, topic_id: str) -> dict | None:
    path = PERSONALIZED_DIR / f"{user_id}_{topic_id}.json"
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


class QuizSubmission(BaseModel):
    quiz_id: str
    topic_id: str
    answers: dict[str, int]
    time_taken_seconds: int | None = Field(default=None, ge=0)


def _grade_quiz_questions(quiz_questions: list, answers: dict) -> tuple[list, int, int]:
    results = []
    correct = 0
    for q in quiz_questions:
        qid = q["id"]
        user_answer = answers.get(qid)
        correct_answer = q["answer"]
        is_correct = user_answer == correct_answer
        if is_correct:
            correct += 1
        results.append({
            "question_id": qid,
            "question": q["question"],
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "correct_option_text": q["options"][correct_answer],
            "is_correct": is_correct,
            "explanation": q.get("explanation", ""),
        })
    return results, correct, len(quiz_questions)


@router.get("/quiz")
async def get_quiz(
    topic_id: str,
    personalized: bool = False,
    current_user: dict = Depends(get_current_user),
):
    quizzes = load_quizzes()
    quiz = next((q for q in quizzes.values() if q["topic_id"] == topic_id), None)
    if not quiz:
        raise HTTPException(status_code=404, detail="No quiz found for this topic.")

    questions_full: list = [dict(q) for q in quiz["questions"]]
    quiz_id_out = quiz["id"]

    topic_name = topic_id
    if personalized:
        tf = DATA_DIR / "topics.json"
        if tf.exists():
            with open(tf) as f:
                topics = json.load(f)
            for t in topics:
                if t["id"] == topic_id:
                    topic_name = t.get("name", topic_id)
                    break

        extra = await build_extra_questions_for_topic(
            user_id=current_user["id"],
            topic_id=topic_id,
            topic_name=topic_name,
            enrolled_subject_ids=current_user.get("selected_subjects", []),
            base_count=len(questions_full),
            num_extra=6,
        )
        if not extra:
            # Gracefully fall back to standard quiz when AI is unavailable
            personalized = False
        else:
            questions_full.extend(extra)
            _save_personalized_bank(current_user["id"], topic_id, questions_full)
            quiz_id_out = f"{PERSONAL_PREFIX}{topic_id}"

    safe_questions = [
        {"id": q["id"], "question": q["question"], "options": q["options"]}
        for q in questions_full
    ]

    return {
        "quiz_id": quiz_id_out,
        "topic_id": topic_id,
        "title": quiz["title"] + (" (Personalized)" if personalized else ""),
        "total_questions": len(safe_questions),
        "questions": safe_questions,
        "personalized": personalized,
    }


@router.post("/submit-quiz")
async def submit_quiz(submission: QuizSubmission, current_user: dict = Depends(get_current_user)):
    uid = current_user["id"]
    quizzes = load_quizzes()

    if submission.quiz_id.startswith(PERSONAL_PREFIX):
        t_id = submission.quiz_id.removeprefix(PERSONAL_PREFIX)
        if t_id != submission.topic_id:
            raise HTTPException(status_code=400, detail="Topic does not match personalized quiz.")
        bank = _load_personalized_bank(uid, submission.topic_id)
        if not bank:
            raise HTTPException(status_code=404, detail="Personalized quiz expired. Start the quiz again.")
        quiz_questions = bank["questions"]
    else:
        quiz = quizzes.get(submission.quiz_id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        quiz_questions = quiz["questions"]

    results, correct_count, total = _grade_quiz_questions(quiz_questions, submission.answers)
    score_pct = round((correct_count / total * 100), 1) if total > 0 else 0.0

    attempt = {
        "attempt_id": str(uuid.uuid4()),
        "user_id": uid,
        "quiz_id": submission.quiz_id,
        "topic_id": submission.topic_id,
        "score": correct_count,
        "total": total,
        "score_pct": score_pct,
        "answers": submission.answers,
        "time_taken_seconds": submission.time_taken_seconds,
        "submitted_at": datetime.utcnow().isoformat(),
    }

    attempts = load_attempts()
    if uid not in attempts:
        attempts[uid] = {}
    topic_attempts = attempts[uid].get(submission.topic_id, [])
    topic_attempts.append(attempt)
    attempts[uid][submission.topic_id] = topic_attempts
    save_attempts(attempts)

    progress = load_progress()
    if uid not in progress:
        progress[uid] = {"topics": {}}
    if "topics" not in progress[uid]:
        progress[uid]["topics"] = {}
    if submission.topic_id not in progress[uid]["topics"]:
        progress[uid]["topics"][submission.topic_id] = {}

    topic_progress = progress[uid]["topics"][submission.topic_id]
    all_scores = topic_progress.get("quiz_scores", [])
    all_scores.append(score_pct)
    topic_progress["quiz_scores"] = all_scores
    topic_progress["latest_quiz_score"] = score_pct
    topic_progress["quiz_attempts_count"] = len(all_scores)
    topic_progress["best_quiz_score"] = max(all_scores)
    topic_progress["avg_quiz_score"] = round(sum(all_scores) / len(all_scores), 1)
    topic_progress["last_quiz_at"] = datetime.utcnow().isoformat()
    save_progress(progress)

    if score_pct >= 80:
        feedback = "Excellent! You have a strong grasp of this topic."
    elif score_pct >= 60:
        feedback = "Good job! Review the explanations for the questions you missed."
    elif score_pct >= 40:
        feedback = "Keep going! Focus on the weak areas highlighted below."
    else:
        feedback = "Don't give up! We recommend revisiting the learning resources first."

    weak = detect_weak_topics(uid, current_user.get("selected_subjects", []))
    weak_summary = "; ".join(f"{w['topic_name']}: {w['overall_progress_pct']}%" for w in weak[:6])
    ai_note = await personalized_quiz_result_message(
        full_name=current_user.get("full_name", "Student"),
        topic_name=submission.topic_id,
        score_pct=score_pct,
        weak_topics_summary=weak_summary or "Still mapping your strengths.",
    )

    return {
        "attempt_id": attempt["attempt_id"],
        "score": correct_count,
        "total": total,
        "score_pct": score_pct,
        "feedback": feedback,
        "personalized_feedback": ai_note,
        "results": results,
    }


@router.get("/quiz/attempts/{topic_id}")
def get_quiz_attempts(topic_id: str, current_user: dict = Depends(get_current_user)):
    attempts = load_attempts()
    topic_attempts = attempts.get(current_user["id"], {}).get(topic_id, [])
    topic_attempts.sort(key=lambda a: a["submitted_at"], reverse=True)
    return {"topic_id": topic_id, "attempts": topic_attempts}
