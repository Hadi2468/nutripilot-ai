import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import UserData
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Plan Endpoint
# ============================================================

@router.post("/v1/nutripilot/plan")
async def generate_diet_plan(
    user_data: UserData,
    token: str = Depends(verify_token),
):
    """
    Generate a personalized seven-day diet plan.
    """

    try:
        prompt = f"""
Create a personalized weekly diet plan.

User information:
- Meal preference: {user_data.meal_preference}
- Daily calories: {user_data.calories}
- Meals per day: {user_data.meal_count}
- Diseases: {user_data.diseases or "None"}
- Goal: {user_data.goal}
- Age: {user_data.age}
- Dislikes: {user_data.dislikes or "None"}
- Preferred foods: {user_data.preferred_foods or "None"}

Provide a Day 1 to Day 7 plan using homemade food.
"""

        response = call_llm(
            system_prompt=(
                "You are an expert Indian dietitian. "
                "Create practical homemade meal plans."
            ),
            user_prompt=prompt,
        )

        return {
            "type": "weekly_plan",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to generate diet plan")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )