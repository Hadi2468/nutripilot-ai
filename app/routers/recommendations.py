import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Recommendations Endpoint
# ============================================================

@router.get("/v1/nutripilot/recommendations")
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