import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import UserData
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Meal Endpoint
# ============================================================

@router.post("/v1/nutripilot/meal")
async def suggest_meal(
    user_data: UserData,
    token: str = Depends(verify_token),
):
    """
    Suggest a single healthy meal based on the user's goal.
    """

    try:
        prompt = (
            f"Suggest one healthy meal for {user_data.goal} "
            f"within {user_data.calories} calories."
        )

        response = call_llm(
            system_prompt="You are a diet expert.",
            user_prompt=prompt,
        )

        return {
            "type": "single_meal",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to generate meal suggestion")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )