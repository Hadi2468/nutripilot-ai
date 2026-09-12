import logging
from typing import Optional

from app.core.config import API_TOKEN
from app.core.security import verify_token
from app.models.schemas import FoodInput, ModifyPlanInput, UserData
from app.routers.recommendations import router as recommendations_router
from app.routers.plan import router as plan_router
from app.routers.meal import router as meal_router
from app.routers.regenerate import router as regenerate_router
from app.routers.substitute import router as substitute_router
from app.routers.analysis import router as analysis_router
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
app.include_router(regenerate_router)
app.include_router(substitute_router)
app.include_router(analysis_router)


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
# AWS Lambda Handler
# ============================================================

handler = Mangum(app)
