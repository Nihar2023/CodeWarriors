"""LLM helpers for quiz personalization (Gemini)."""

from __future__ import annotations

import json
import re
from typing import Any

from utils.llm_client import generate_text, llm_configured
from utils.progress_calculator import calculate_topic_progress
from utils.weak_area_detector import detect_weak_topics


async def build_extra_questions_for_topic(
    *,
    user_id: str,
    topic_id: str,
    topic_name: str,
    enrolled_subject_ids: list[str],
    base_count: int,
    num_extra: int = 6,
) -> list[dict[str, Any]]:
    """Return full question dicts (with id, question, options, answer, explanation)."""
    if not llm_configured() or num_extra <= 0:
        return []

    weak = detect_weak_topics(user_id, enrolled_subject_ids)
    tp = calculate_topic_progress(user_id, topic_id)
    weak_note = "; ".join(
        f"{w['topic_name']} ({w['overall_progress_pct']}%)" for w in weak[:4]
    ) or "No weak topics flagged yet."

    prompt = f"""
You are an expert CS educator. Create exactly {num_extra} multiple-choice questions
for the topic "{topic_name}" (topic_id: {topic_id}).

Student context:
- Overall progress on this topic: {tp['overall_progress_pct']}%
- Resource completion: {tp['resource_completion_pct']}%
- Avg quiz score so far: {tp['avg_quiz_score'] if tp['has_quiz_attempt'] else 'not yet attempted'}
- Other weak areas: {weak_note}

Difficulty: match the student's level (easier if progress/quiz low; harder if strong).
Each question must have exactly 4 options, one correct answer.

Return JSON array only, format:
[
  {{
    "id": "gen_1",
    "question": "...",
    "options": ["A","B","C","D"],
    "answer": 0,
    "explanation": "short explanation"
  }}
]
Use ids gen_1 through gen_{num_extra}. Base question count in bank was {base_count}.
""".strip()

    raw = await generate_text(prompt, temperature=0.45)
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Gemini quiz JSON must be an array")
    out = []
    for i, item in enumerate(data[:num_extra]):
        qid = item.get("id") or f"gen_{i+1}"
        options = item.get("options") or []
        if len(options) != 4:
            continue
        ans = int(item.get("answer", 0))
        out.append({
            "id": qid,
            "question": str(item.get("question", "")).strip(),
            "options": [str(o) for o in options],
            "answer": max(0, min(3, ans)),
            "explanation": str(item.get("explanation", "")).strip() or "See course materials.",
        })
    return out


async def personalized_quiz_result_message(
    *,
    full_name: str,
    topic_name: str,
    score_pct: float,
    weak_topics_summary: str,
) -> str:
    if not llm_configured():
        return ""
    prompt = f"""
Student name: {full_name}
Topic: {topic_name}
Quiz score: {score_pct}%
Known weak areas / context: {weak_topics_summary}

Write 2–3 short sentences of personalized feedback: what to review next,
study pace, and encouragement. No markdown.
""".strip()
    return (await generate_text(prompt, temperature=0.55)).strip()


async def personalized_resource_intro(
    *,
    full_name: str,
    topic_name: str,
    resource_title: str,
    resource_type: str,
    user_progress_pct: float,
    weak_hint: str,
) -> str:
    if not llm_configured():
        return ""
    prompt = f"""
Learner: {full_name}
Topic: {topic_name}
Resource: "{resource_title}" (type: {resource_type})
Their topic progress: {user_progress_pct}%
Weak-area hint: {weak_hint}

One short paragraph (max 80 words): why this resource helps them now and how to use it.
No markdown.
""".strip()
    return (await generate_text(prompt, temperature=0.5)).strip()
