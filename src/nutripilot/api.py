"""FastAPI service; `handler` is the AWS Lambda entry point (API Gateway -> Mangum).

Run locally:  uvicorn nutripilot.api:app --reload
"""

from __future__ import annotations

import logging
import os
import secrets
import threading
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from mangum import Mangum

from nutripilot import __version__
from nutripilot.config import (
    CATALOG,
    DEFAULT_MODELS,
    MODEL_CATALOG,
    Provider,
    Settings,
    get_settings,
    provider_of,
)
from nutripilot.llm import ChatModel, LLMError, LLMRateLimitError, build_chat_model
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

ModelBuilder = Callable[[Provider, str], ChatModel]


class ModelRegistry:
    """Builds each chat model on first use and reuses it. Models are only built when asked
    for, so importing the app (tests, Lambda cold start) never needs API keys."""

    def __init__(self, settings: Settings, builder: ModelBuilder | None = None):
        self.settings = settings
        self.builder = builder or (lambda p, m: build_chat_model(settings, p, m))
        self._models: dict[tuple[str, str], ChatModel] = {}
        self._lock = threading.Lock()

    def default(self) -> tuple[Provider, str]:
        return self.settings.provider, self.settings.resolved_model

    def resolve(self, provider: Provider | None, model: str | None) -> tuple[Provider, str]:
        """Fill in whichever half is missing and check the pair against the catalog."""
        if provider is None and model is None:
            return self.default()
        if provider is None:
            provider = provider_of(model) if model else None
            if provider is None:
                raise HTTPException(422, f"Unknown model '{model}'")
        if model is None:
            default_provider, default_model = self.default()
            model = default_model if provider == default_provider else DEFAULT_MODELS[provider]
        if (provider, model) != self.default() and model not in MODEL_CATALOG[provider]:
            raise HTTPException(422, f"Model '{model}' is not offered for provider '{provider}'")
        return provider, model

    def get(self, provider: Provider, model: str) -> ChatModel:
        with self._lock:
            if (provider, model) not in self._models:
                self._models[(provider, model)] = self.builder(provider, model)
            return self._models[(provider, model)]

    def catalog(self) -> dict[str, Any]:
        default_provider, default_model = self.default()
        return {
            "default": {"provider": default_provider, "model": default_model},
            "models": [
                {
                    "platform": spec.platform,
                    "provider": spec.provider,
                    "family": spec.family,
                    "model": spec.model,
                    "label": spec.label,
                    "available": bool(self.settings.provider_api_key(spec.provider)),
                }
                for spec in CATALOG
            ],
        }


def get_service(
    request: Request,
    provider: Annotated[Provider | None, Query(description="LLM provider for this request")] = None,
    model: Annotated[str | None, Query(max_length=100, description="Catalog model ID")] = None,
) -> NutriPilotService:
    state = request.app.state
    registry: ModelRegistry = state.models
    provider, model = registry.resolve(provider, model)
    if state.service is not None and (provider, model) == registry.default():
        return state.service
    return NutriPilotService(registry.get(provider, model), state.settings)


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


@router.get("/models", tags=["models"])
def models(request: Request) -> dict[str, Any]:
    """The models a client may choose per request (`?provider=&model=`), and which are
    available because their provider's API key is configured."""
    return request.app.state.models.catalog()


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
    service: NutriPilotService | None = None,
    settings: Settings | None = None,
    model_builder: ModelBuilder | None = None,
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or get_settings()

    app = FastAPI(
        title="NutriPilot AI",
        description="Structured, validated nutrition planning with LLMs",
        version=__version__,
    )
    app.state.settings = settings
    app.state.service = service  # injected default-model service (tests); else built lazily
    app.state.models = ModelRegistry(settings, model_builder)

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
