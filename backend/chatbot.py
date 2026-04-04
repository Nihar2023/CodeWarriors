"""
Learning assistant chat — Gemini (Google Generative Language API).
Auto-detects intent: doubt solving, concept explanation, or resource suggestion.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from utils.llm_client import active_llm_provider, generate_text, llm_configured

DATA_DIR = Path(__file__).parent.parent / "data"
CHAT_HISTORY_FILE = DATA_DIR / "chat_history.json"

router = APIRouter()


def load_chat_history() -> dict:
    if not CHAT_HISTORY_FILE.exists():
        return {}
    with open(CHAT_HISTORY_FILE) as f:
        return json.load(f)


def save_chat_history(history: dict) -> None:
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def detect_chat_mode(message: str) -> str:
    m = message.lower()
    if any(k in m for k in ("resource", "material", "link", "video", "pdf", "article", "where can i read")):
        return "resource_suggestion"
    if any(k in m for k in ("error", "bug", "wrong", "fix this", "not working", "stuck on", "why is my")):
        return "doubt_solving"
    return "concept_explanation"


class ChatMessage(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None


MODE_INSTRUCTIONS = {
    "doubt_solving": (
        "Mode: DOUBT SOLVING. The student has a concrete problem or confusion. "
        "Diagnose likely causes, give a clear step-by-step fix, and one sanity check. "
        "If code is present, comment on the most probable mistake first."
    ),
    "concept_explanation": (
        "Mode: CONCEPT EXPLANATION. Explain the CS concept clearly with a tiny example "
        "(Python or JavaScript as appropriate). Avoid unnecessary jargon."
    ),
    "resource_suggestion": (
        "Mode: RESOURCE SUGGESTION. Suggest specific resource types (official docs, MDN, "
        "Real Python, video course, practice sites) the student can use. Include exact search "
        "queries or canonical URLs where possible. Keep it actionable."
    ),
}


@router.post("/chat")
async def chat(req: ChatMessage, current_user: dict = Depends(get_current_user)):
    if not llm_configured():
        raise HTTPException(
            status_code=503,
            detail="Chat requires GROQ_API_KEY or GEMINI_API_KEY in the server environment.",
        )

    uid = current_user["id"]
    session_id = req.session_id or str(uuid.uuid4())
    mode = detect_chat_mode(req.message)
    mode_instruction = MODE_INSTRUCTIONS[mode]

    history_data = load_chat_history()
    if uid not in history_data:
        history_data[uid] = {}
    if session_id not in history_data[uid]:
        history_data[uid][session_id] = []

    conversation = history_data[uid][session_id]

    # Compact history for prompt (last turns)
    hist_lines = []
    for msg in conversation[-12:]:
        role = msg.get("role", "")
        prefix = "Student" if role == "user" else "Tutor"
        hist_lines.append(f"{prefix}: {msg.get('content', '')}")

    history_blob = "\n".join(hist_lines) if hist_lines else "(no prior messages)"

    prompt = f"""
{mode_instruction}

Student display name: {current_user.get('full_name', 'Student')}
Learning goals (if any): {current_user.get('profile', {}).get('learning_goals', 'n/a')}

Recent conversation:
{history_blob}

Latest message: {req.message}

Reply helpfully in plain text (no markdown code fences). Under 200 words unless the doubt requires more.
""".strip()

    try:
        bot_response = await generate_text(prompt, temperature=0.55)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    timestamp = datetime.utcnow().isoformat()
    conversation.append({"role": "user", "content": req.message, "timestamp": timestamp, "detected_mode": mode})
    conversation.append({"role": "assistant", "content": bot_response, "timestamp": timestamp})
    history_data[uid][session_id] = conversation[-50:]
    save_chat_history(history_data)

    return {
        "session_id": session_id,
        "response": bot_response,
        "detected_mode": mode,
        "source": active_llm_provider() or "llm",
        "timestamp": timestamp,
    }


@router.get("/chat/history")
def get_chat_history(session_id: str | None = None, current_user: dict = Depends(get_current_user)):
    history_data = load_chat_history()
    user_history = history_data.get(current_user["id"], {}) or {}

    if session_id:
        messages = user_history.get(session_id, [])
        normalized = []
        for msg in messages:
            normalized.append(
                {
                    "role": msg.get("role"),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp"),
                    "detected_mode": msg.get("detected_mode"),
                }
            )
        return {"session_id": session_id, "messages": normalized}

    sessions_out = []
    for sid, msgs in user_history.items():
        sessions_out.append(
            {
                "session_id": sid,
                "message_count": len(msgs),
                "last_message": msgs[-1]["timestamp"] if msgs else None,
            }
        )
    sessions_out.sort(key=lambda s: s["last_message"] or "", reverse=True)
    return {"sessions": sessions_out}


@router.delete("/chat/history/{session_id}")
def clear_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    history_data = load_chat_history()
    if current_user["id"] in history_data:
        history_data[current_user["id"]].pop(session_id, None)
        save_chat_history(history_data)
    return {"message": "Session cleared."}
