"""FastAPI service; `handler` is the AWS Lambda entry point (API Gateway -> Mangum).

Run locally:  uvicorn nutripilot.api:app --reload
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mangum import Mangum

from nutripilot import __version__
from nutripilot.config import Settings, get_settings
from nutripilot.llm import LLMError, LLMRateLimitError
from nutripilot.schemas import (
    Envelope,
    FoodInput,
    Goal,
    Meal,
    MealRequest,
    NutritionAnalysis,
    PlanRequest,
    RegenerateRequest,
    SubstituteRequest,
    Substitutions,
    Tips,
    WeeklyPlan,
)
from nutripilot.service import NutriPilotService, OutputValidationError

logger = logging.getLogger(__name__)
PREFIX = "/v1/nutripilot"


# ============================================================
# Dependencies
# ============================================================

_service_lock = threading.Lock()


def get_service(request: Request) -> NutriPilotService:
    # Built on first use, so importing the app (tests, Lambda cold start) never needs keys.
    state = request.app.state
    with _service_lock:
        if state.service is None:
            state.service = NutriPilotService.from_settings(state.settings)
    return state.service


def require_token(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
) -> None:
    settings: Settings = request.app.state.settings
    expected = settings.api_token
    if not expected:
        if settings.auth_required:
            logger.error("auth_required is set but no API token is configured")
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication misconfigured")
        return
    if creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


ServiceDep = Annotated[NutriPilotService, Depends(get_service)]


# ============================================================
# Routes
# ============================================================

# Sync handlers: FastAPI runs them in a threadpool, so a slow LLM call
# doesn't block the event loop.
router = APIRouter(prefix=PREFIX, dependencies=[Depends(require_token)], tags=["nutrition"])


@router.post("/plan", response_model=Envelope[WeeklyPlan])
def plan(req: PlanRequest, svc: ServiceDep) -> Envelope[WeeklyPlan]:
    """Seven-day plan; daily calories, meal count and excluded foods are checked in code."""
    return svc.plan(req)


@router.post("/plan/regenerate", response_model=Envelope[WeeklyPlan])
def regenerate(req: RegenerateRequest, svc: ServiceDep) -> Envelope[WeeklyPlan]:
    """Revise an existing plan; the result is held to the same checks as a new plan."""
    return svc.regenerate(req)


@router.post("/meal", response_model=Envelope[Meal])
def meal(req: MealRequest, svc: ServiceDep) -> Envelope[Meal]:
    """One meal for a calorie target."""
    return svc.meal(req)


@router.post("/analysis", response_model=Envelope[NutritionAnalysis])
def analysis(req: FoodInput, svc: ServiceDep) -> Envelope[NutritionAnalysis]:
    """Per-item nutrient estimates; totals are summed in code."""
    return svc.analyze(req.food_items)


@router.post("/substitute", response_model=Envelope[Substitutions])
def substitute(req: SubstituteRequest, svc: ServiceDep) -> Envelope[Substitutions]:
    """Healthier swaps that respect allergies and dislikes."""
    return svc.substitute(req)


@router.get("/recommendations", response_model=Envelope[Tips])
def recommendations(
    svc: ServiceDep, goal: Annotated[Goal | None, Query()] = None
) -> Envelope[Tips]:
    """Five healthy eating tips, optionally for a goal."""
    return svc.tips(goal)


# ============================================================
# App factory
# ============================================================


def create_app(
    service: NutriPilotService | None = None, settings: Settings | None = None
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or get_settings()

    app = FastAPI(
        title="NutriPilot AI",
        description="Structured, validated nutrition planning with LLMs",
        version=__version__,
    )
    app.state.settings = settings
    app.state.service = service

    @app.get("/", tags=["ops"])
    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.exception_handler(OutputValidationError)
    def _invalid_output(_: Request, exc: OutputValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "detail": "The AI response failed validation. Please try again.",
                "problems": exc.problems,
            },
        )

    @app.exception_handler(LLMRateLimitError)
    def _rate_limited(_: Request, exc: LLMRateLimitError) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    def _llm_unavailable(_: Request, exc: LLMError) -> JSONResponse:
        logger.error("LLM error: %s", exc)
        return JSONResponse(
            status_code=503, content={"detail": "The AI service is temporarily unavailable."}
        )

    app.include_router(router)
    return app


app = create_app()

# AWS Lambda entry point (template.yaml: Handler: nutripilot.api.handler). A named HTTP API
# stage prefixes every path (/prod/health), so the stage is stripped before routing.
handler = Mangum(app, lifespan="off", api_gateway_base_path=os.getenv("NUTRIPILOT_BASE_PATH", "/"))
