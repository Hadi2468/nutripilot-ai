import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import FoodInput
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Food Analysis Endpoint
# ============================================================

@router.post("/v1/nutripilot/analysis")
async def analyze_food(
    data: FoodInput,
    token: str = Depends(verify_token),
):
    """
    Analyze the nutritional value of specified foods.
    """

    try:
        prompt = (
            f"Analyze the nutritional value of: "
            f"{data.food_items}"
        )

        response = call_llm(
            system_prompt=(
                "You are a nutrition expert. "
                "Provide calories, protein, carbohydrates, and fats."
            ),
            user_prompt=prompt,
        )

        return {
            "type": "analysis",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to analyze food")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )