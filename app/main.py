import logging
from typing import Optional

from app.core.config import API_TOKEN
from app.core.security import verify_token
from app.models.schemas import FoodInput, ModifyPlanInput, UserData
from app.routers.recommendations import router as recommendations_router
from app.routers.plan import router as plan_router
from app.routers.meal import router as meal_router
from app.services.llm_service import call_llm

from fastapi import Depends, FastAPI, HTTPException
from mangum import Mangum


# ============================================================
# Logging
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="AI Diet Planner API",
    description="AI-powered diet planning and nutrition analysis API",
    version="1.0.0",
)

app.include_router(recommendations_router)
app.include_router(plan_router)
app.include_router(meal_router)


# ============================================================
# Health Check
# ============================================================

@app.get("/")
async def root():
    """
    Health-check endpoint.
    """

    return {
        "message": "API is live"
    }


@app.post("/v1/nutripilot/plan/regenerate")
async def regenerate_plan(
    data: ModifyPlanInput,
    token: str = Depends(verify_token),
):
    """
    Modify an existing diet plan based on a user's request.
    """

    try:
        prompt = f"""
Modify the following diet plan:

Existing plan:
{data.existing_plan}

Modification request:
{data.modification_request}
"""

        response = call_llm(
            system_prompt=(
                "You are a dietitian who adjusts meal plans "
                "based on user needs."
            ),
            user_prompt=prompt,
        )

        return {
            "type": "modified_plan",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to regenerate diet plan")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )


# ============================================================
# Food & Nutrition Endpoints
# ============================================================

@app.post("/v1/nutripilot/substitute")
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


@app.post("/v1/nutripilot/analysis")
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


# ============================================================
# AWS Lambda Handler
# ============================================================

handler = Mangum(app)
