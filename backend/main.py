"""
main.py — SmartLearn AI FastAPI Application Entry Point.

Registers all routers and configures CORS so the React frontend
(running on localhost:3000) can talk to this backend (localhost:8000).
"""

from pathlib import Path

from dotenv import load_dotenv

# Load `.env` from project root before any code reads os.environ
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import all route modules (after dotenv so SECRET_KEY / LLM env vars are available)
from backend import auth, subjects, resources, quiz, analytics, recommendations, chatbot, games, entry_quiz, learning_path

app = FastAPI(
    title="SmartLearn AI",
    description="AI-powered personalized learning platform for CS students",
    version="1.0.0",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
_cors_raw = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500,null",
)
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r".*",  # allow any origin for local dev
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ───────────────────────────────────────────────────────────
app.include_router(auth.router, tags=["Authentication"])
app.include_router(subjects.router, tags=["Subjects & Topics"])
app.include_router(resources.router, tags=["Resources"])
app.include_router(quiz.router, tags=["Quiz"])
app.include_router(analytics.router, tags=["Dashboard & Analytics"])
app.include_router(recommendations.router, tags=["Recommendations"])
app.include_router(chatbot.router, tags=["Chatbot"])
app.include_router(games.router, tags=["Games"])
app.include_router(entry_quiz.router, tags=["Entry Assessment"])
app.include_router(learning_path.router, tags=["Learning Path"])


# ── Health Check ───────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "SmartLearn AI backend is running."}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
