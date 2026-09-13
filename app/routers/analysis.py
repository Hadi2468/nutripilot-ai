import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import FoodInput
from app.services.llm_service import call_llm
from app.services.validators import parse_nutrition_analysis_output

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
            "Analyze the nutritional value of the following foods and "
            "return ONLY valid JSON with these numeric fields: "
            "calories, protein, carbohydrates, fat. "
            "Do not include markdown, explanations, or code fences.\n\n"
            f"Food items: {data.food_items}"
        )

        response = call_llm(
            system_prompt=(
                "You are a nutrition expert. "
                "Provide calories, protein, carbohydrates, and fats."
            ),
            user_prompt=prompt,
        )



        parsed = parse_nutrition_analysis_output(response)

        if parsed is None:
            logger.warning("LLM returned invalid structured nutrition analysis")

            raise HTTPException(
                status_code=502,
                detail="The AI generated an invalid nutrition analysis.",
            )

        return {
            "type": "analysis",
            "data": parsed.model_dump(),
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to analyze food")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )