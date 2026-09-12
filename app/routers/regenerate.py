import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import verify_token
from app.models.schemas import ModifyPlanInput
from app.services.llm_service import call_llm


logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# NutriPilot Plan Regeneration Endpoint
# ============================================================

@router.post("/v1/nutripilot/plan/regenerate")
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