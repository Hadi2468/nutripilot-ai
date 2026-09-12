import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import FoodInput
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Food & Nutrition Endpoint
# ============================================================

@router.post("/v1/nutripilot/substitute")
async def substitute_food(
    data: FoodInput,
    token: str = Depends(verify_token),
):
    """
    Suggest healthy alternatives for specified foods.
    """

    try:
        prompt = (
            f"Suggest healthy alternatives for: "
            f"{data.food_items}"
        )

        response = call_llm(
            system_prompt=(
                "You are a nutritionist suggesting "
                "healthy food substitutions."
            ),
            user_prompt=prompt,
        )

        return {
            "type": "substitution",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to generate food substitutions")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )

