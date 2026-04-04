"""
Personalized recommendations via configured LLM (Groq or Gemini; no rule-based fallback).
"""

from __future__ import annotations

import json
import re

from utils.llm_client import generate_text, llm_configured
from utils.progress_calculator import calculate_topic_progress
from utils.weak_area_detector import detect_weak_topics, topic_mastery_report


async def get_ai_recommendations(user_id: str, subject_ids: list[str]) -> list[dict]:
    if not subject_ids:
        return []

    if not llm_configured():
        raise RuntimeError(
            "Recommendations require GROQ_API_KEY or GEMINI_API_KEY. Set one in your environment."
        )

    weak = detect_weak_topics(user_id, subject_ids)
    mastery = topic_mastery_report(user_id, subject_ids)

    lines = []
    for m in mastery[:40]:
        lines.append(
            f"- {m['topic_name']} ({m['subject_name']}): overall {m['overall_progress_pct']}%, "
            f"strength={m['strength_category']}, resources {m['resource_completion_pct']}%, "
            f"avg_quiz={m['avg_quiz_score']}"
        )

    weak_lines = [f"- {w['topic_name']}: {', '.join(w['reasons'])}" for w in weak[:15]]

    prompt = f"""
You are SmartLearn AI's learning coach for CS students (Python & JavaScript).

Student progress by topic:
{chr(10).join(lines) if lines else '(no topics yet)'}

Weak-area flags:
{chr(10).join(weak_lines) if weak_lines else '(none)'}

Return JSON only (no markdown), an array of 5–8 objects:
[
  {{"title": "short title", "detail": "actionable 1-2 sentences", "topic_id": "optional_topic_id_or_empty"}},
]

Rules:
- Prioritize weak topics and low quiz performance.
- Mention learning pace (e.g. bite-sized sessions) when appropriate.
- Be specific to the topics above; do not invent unrelated subjects.
""".strip()

    raw = await generate_text(prompt, temperature=0.4)
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Recommendations JSON must be an array")

    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        detail = str(item.get("detail", "")).strip()
        if not title or not detail:
            continue
        tid = item.get("topic_id") or ""
        out.append({"title": title, "detail": detail, "topic_id": tid or None})
    return out
