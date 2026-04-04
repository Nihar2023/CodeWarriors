"""
recommendations.py — REST endpoint for the recommendation engine.
"""

from fastapi import APIRouter, Depends, HTTPException
from backend.auth import get_current_user
from utils.recommendation_engine import get_ai_recommendations

router = APIRouter()


@router.get("/recommendations")
async def get_recommendations(current_user: dict = Depends(get_current_user)):
    """
    Personalized study recommendations (Groq or Gemini). Requires GROQ_API_KEY or GEMINI_API_KEY.
    """
    subject_ids = current_user.get("selected_subjects", [])
    try:
        recommendations = await get_ai_recommendations(current_user["id"], subject_ids)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Recommendation AI failed: {e}") from e
    return {
        "user_id": current_user["id"],
        "recommendations": recommendations,
        "count": len(recommendations),
    }
