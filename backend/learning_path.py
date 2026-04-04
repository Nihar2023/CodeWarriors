"""LLM-generated learning pathway (Groq or Gemini)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from utils.llm_client import generate_text, llm_configured, parse_json_from_llm
from utils.weak_area_detector import detect_weak_topics, topic_mastery_report

router = APIRouter()

# Gemini structured output (REST: generationConfig.responseJsonSchema)
_LEARNING_PATH_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One paragraph overview of the learning path.",
        },
        "steps": {
            "type": "array",
            "description": "Ordered pathway steps grouped by day ranges.",
            "items": {
                "type": "object",
                "properties": {
                    "day_range": {"type": "string", "description": 'e.g. "1-3"'},
                    "focus": {"type": "string", "description": "Topic or theme for this segment."},
                    "tasks": {"type": "array", "items": {"type": "string"}},
                    "checkpoint": {"type": "string", "description": "How to verify understanding."},
                },
                "required": ["day_range", "focus", "tasks", "checkpoint"],
            },
        },
    },
    "required": ["summary", "steps"],
}


class PathRequest(BaseModel):
    days: int = Field(ge=1, le=365, description="Length of the learning plan in days")


@router.post("/learning-path")
async def generate_learning_path(req: PathRequest, current_user: dict = Depends(get_current_user)):
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="Configure GROQ_API_KEY or GEMINI_API_KEY for learning path generation.",
        )

    subjects = current_user.get("selected_subjects", [])
    if not subjects:
        raise HTTPException(status_code=400, detail="Enroll in subjects first.")

    uid = current_user["id"]
    mastery = topic_mastery_report(uid, subjects)
    weak = detect_weak_topics(uid, subjects)
    profile = current_user.get("profile") or {}
    goals = profile.get("learning_goals") or "General CS fluency"
    level = current_user.get("skill_level") or "not assessed"

    lines = [f"- {m['topic_name']}: {m['strength_category']} ({m['overall_progress_pct']}%)" for m in mastery]
    weak_lines = [f"- {w['topic_name']}: {'; '.join(w['reasons'])}" for w in weak]

    prompt = f"""
Create a step-by-step learning pathway for a college CS student.

Profile:
- Name: {current_user.get('full_name')}
- Stated goals: {goals}
- Skill level (from entry quiz): {level}
- Plan length: {req.days} days

Enrolled topic mastery:
{chr(10).join(lines)}

Weak areas:
{chr(10).join(weak_lines) if weak_lines else '(none flagged)'}

Include {min(req.days, 30)} steps or fewer but cover the full {req.days}-day horizon by grouping days.
Order steps from foundational to advanced based on weak areas first.
""".strip()

    raw = await generate_text(
        prompt,
        temperature=0.35,
        response_mime_type="application/json",
        response_json_schema=_LEARNING_PATH_JSON_SCHEMA,
    )
    try:
        data = parse_json_from_llm(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI returned invalid JSON for learning path.") from exc

    return {"user_id": uid, "days": req.days, "path": data}
