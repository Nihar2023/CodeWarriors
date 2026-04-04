"""
Topic-based interactive learning games (fully embedded — data served by API, UI in frontend).
No external game platforms; educational content is curated per topic.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth import get_current_user

DATA_DIR = Path(__file__).parent.parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"

router = APIRouter()

# Curated per-topic game payloads (embedded experiences; play happens in-app).
TOPIC_PLAYSETS: dict[str, list[dict]] = {
    "js_dsa": [
        {
            "game_id": "concept_match_js_dsa",
            "kind": "matching",
            "title": "DSA Term Match",
            "description": "Match JavaScript / DSA terms to definitions.",
            "topic_id": "js_dsa",
            "pairs": [
                {"term": "Big O", "definition": "Describes algorithm growth vs input size"},
                {"term": "Stack", "definition": "LIFO collection; push and pop"},
                {"term": "Queue", "definition": "FIFO collection; enqueue and dequeue"},
                {"term": "Binary Search", "definition": "Halve sorted array each step"},
            ],
        },
        {
            "game_id": "order_blocks_js_dsa",
            "kind": "block_order",
            "title": "Syntax Order: Binary Search Step",
            "description": "Arrange steps to describe one binary search iteration.",
            "topic_id": "js_dsa",
            "blocks": [
                "Compare target with middle element",
                "If target < mid, search left half",
                "If target > mid, search right half",
                "Repeat until found or empty",
            ],
            "correct_order": [0, 1, 2, 3],
        },
        {
            "game_id": "speed_tf_js_dsa",
            "kind": "true_false",
            "title": "DSA Quick Checks",
            "topic_id": "js_dsa",
            "questions": [
                {"statement": "Array index access is O(1) in JS engines.", "answer": True},
                {"statement": "Queue is LIFO.", "answer": False},
                {"statement": "Merge sort is O(n log n) in typical implementations.", "answer": True},
            ],
        },
    ],
    "py_dsa": [
        {
            "game_id": "concept_match_py_dsa",
            "kind": "matching",
            "title": "Python DSA Match",
            "topic_id": "py_dsa",
            "pairs": [
                {"term": "list", "definition": "Ordered mutable sequence"},
                {"term": "dict", "definition": "Key-value hash map"},
                {"term": "deque", "definition": "Double-ended queue from collections"},
                {"term": "heapq", "definition": "Module for min-heap operations"},
            ],
        },
        {
            "game_id": "order_blocks_py_dsa",
            "kind": "block_order",
            "title": "Order: List comprehension filter",
            "topic_id": "py_dsa",
            "blocks": [
                "[x for x in nums",
                "if x % 2 == 0]",
            ],
            "correct_order": [0, 1],
        },
        {
            "game_id": "speed_tf_py_dsa",
            "kind": "true_false",
            "title": "Python facts",
            "topic_id": "py_dsa",
            "questions": [
                {"statement": "Tuples are immutable.", "answer": True},
                {"statement": "Sets allow duplicates.", "answer": False},
            ],
        },
    ],
    "js_oop": [
        {
            "game_id": "concept_match_js_oop",
            "kind": "matching",
            "title": "OOP Terms",
            "topic_id": "js_oop",
            "pairs": [
                {"term": "class", "definition": "Template for object instances"},
                {"term": "prototype", "definition": "Object inheritance chain in JS"},
                {"term": "encapsulation", "definition": "Hide internal state behind APIs"},
            ],
        },
    ],
    "py_oop": [
        {
            "game_id": "concept_match_py_oop",
            "kind": "matching",
            "title": "Python OOP",
            "topic_id": "py_oop",
            "pairs": [
                {"term": "__init__", "definition": "Constructor hook in Python"},
                {"term": "self", "definition": "Instance reference in methods"},
                {"term": "@staticmethod", "definition": "Method decorated to avoid self"},
            ],
        },
    ],
}


def _load_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {}
    with open(PROGRESS_FILE) as f:
        return json.load(f)


def _save_progress(p: dict) -> None:
    with open(PROGRESS_FILE, "w") as f:
        json.dump(p, f, indent=2)


class EmbeddedResult(BaseModel):
    topic_id: str
    game_id: str
    score: float
    accuracy: float = Field(ge=0, le=100)
    attempts: int = Field(ge=0)
    completion_time: float = Field(ge=0)
    completed: bool = True


@router.get("/games/topics/{topic_id}/playsets")
def get_topic_playsets(topic_id: str, current_user: dict = Depends(get_current_user)):
    """Games available for a specific learning topic (embedded)."""
    playsets = TOPIC_PLAYSETS.get(topic_id, [])
    if not playsets:
        raise HTTPException(status_code=404, detail="No embedded games for this topic yet.")
    return {"topic_id": topic_id, "games": playsets}


@router.get("/games/topics")
def list_topics_with_games(current_user: dict = Depends(get_current_user)):
    return {"topic_ids": sorted(TOPIC_PLAYSETS.keys())}


@router.post("/games/embedded/result")
def save_embedded_result(req: EmbeddedResult, current_user: dict = Depends(get_current_user)):
    progress = _load_progress()
    uid = current_user["id"]
    if uid not in progress:
        progress[uid] = {}
    progress[uid].setdefault("embedded_game_results", [])
    progress[uid]["embedded_game_results"].append(
        {
            "topic_id": req.topic_id,
            "game_id": req.game_id,
            "score": req.score,
            "accuracy": req.accuracy,
            "attempts": req.attempts,
            "completion_time": req.completion_time,
            "completed": req.completed,
            "played_at": datetime.utcnow().isoformat(),
        }
    )
    _save_progress(progress)
    return {"message": "Saved.", "result": progress[uid]["embedded_game_results"][-1]}


@router.get("/games/embedded/history")
def embedded_history(current_user: dict = Depends(get_current_user)):
    progress = _load_progress()
    rows = progress.get(current_user["id"], {}).get("embedded_game_results", [])
    rows.sort(key=lambda r: r["played_at"], reverse=True)
    return {"results": rows}
