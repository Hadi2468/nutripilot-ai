import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from groq import Groq
from mangum import Mangum
from pydantic import BaseModel


# ============================================================
# Logging
# ============================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# ============================================================
# Environment Variables
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
API_TOKEN = os.getenv("API_TOKEN")


if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not configured.")

if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not configured.")


# ============================================================
# Groq Client
# ============================================================

client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="AI Diet Planner API",
    description="AI-powered diet planning and nutrition analysis API",
    version="1.0.0",
)


# ============================================================
# Authentication
# ============================================================

security = HTTPBearer()


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """
    Validate the Bearer token provided by the client.
    """

    token = credentials.credentials

    if token != API_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
        )

    return token


# ============================================================
# Request Models
# ============================================================

class UserData(BaseModel):
    meal_preference: str
    calories: int
    meal_count: int
    diseases: Optional[str] = None
    goal: str
    age: int
    dislikes: Optional[str] = None
    preferred_foods: Optional[str] = None


class FoodInput(BaseModel):
    food_items: str


class ModifyPlanInput(BaseModel):
    existing_plan: str
    modification_request: str


# ============================================================
# LLM Service
# ============================================================

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Send a request to the Groq LLM and return the generated response.
    """

    response = client.chat.completions.create(
        # model="llama-3.1-8b-instant",
        model="openai/gpt-oss-20b",
        temperature=0.7,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    return response.choices[0].message.content


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


# ============================================================
# Diet Plan Endpoints
# ============================================================

@app.post("/v1/diet/plan")
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


@app.post("/v1/diet/meal")
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


@app.post("/v1/diet/plan/regenerate")
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

@app.post("/v1/diet/substitute")
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


@app.post("/v1/diet/analyze")
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
# Quick Tips
# ============================================================

@app.get("/v1/diet/tips")
async def quick_tips(
    token: str = Depends(verify_token),
):
    """
    Generate five quick healthy eating tips.
    """

    try:
        response = call_llm(
            system_prompt="You are a health coach.",
            user_prompt="Give 5 quick healthy eating tips.",
        )

        return {
            "type": "tips",
            "data": response,
        }

    except Exception:
        logger.exception("Failed to generate healthy eating tips")

        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again later.",
        )


# ============================================================
# AWS Lambda Handler
# ============================================================

handler = Mangum(app)
