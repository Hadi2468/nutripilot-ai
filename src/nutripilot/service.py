"""Service layer: the single entry point used by the API, the CLI and (through the API) the
dashboard, so every interface behaves identically.

Every feature follows the same loop: prompt -> JSON -> Pydantic -> deterministic checks
-> (repair with the listed problems, bounded) -> response with warnings and metadata.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from nutripilot import checks, prompts
from nutripilot.config import Settings, get_settings
from nutripilot.llm import ChatModel, Message
from nutripilot.policy import CONDITIONS_WARNING, DISCLAIMER
from nutripilot.schemas import (
    Envelope,
    Meal,
    MealRequest,
    Meta,
    NutritionAnalysis,
    PlanRequest,
    RegenerateRequest,
    SubstituteRequest,
    Substitutions,
    Tips,
    WeeklyPlan,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
Check = Callable[[T], list[str]]

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


class OutputValidationError(Exception):
    """The LLM output still failed its checks after the repair budget (HTTP 502)."""

    def __init__(self, kind: str, problems: list[str]):
        super().__init__(f"{kind}: {'; '.join(problems)}")
        self.kind = kind
        self.problems = problems


def _validation_problems(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in err['loc']) or 'root'}: {err['msg']}"
        for err in exc.errors()[:10]
    ]


class NutriPilotService:
    def __init__(self, llm: ChatModel, settings: Settings | None = None):
        self.llm = llm
        self.settings = settings or get_settings()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> NutriPilotService:
        from nutripilot.llm import build_chat_model

        settings = settings or get_settings()
        return cls(build_chat_model(settings), settings)

    # ------------------------------------------------------------
    # Features
    # ------------------------------------------------------------

    def plan(self, req: PlanRequest) -> Envelope[WeeklyPlan]:
        return self._plan("weekly_plan", req, prompts.plan_prompt(req))

    def regenerate(self, req: RegenerateRequest) -> Envelope[WeeklyPlan]:
        prompt = prompts.regenerate_prompt(req.profile, req.existing_plan, req.modification_request)
        return self._plan("modified_plan", req.profile, prompt)

    def meal(self, req: MealRequest) -> Envelope[Meal]:
        tol = self.settings.calorie_tolerance
        meal, meta = self._generate(
            "single_meal", prompts.meal_prompt(req), Meal, lambda m: checks.check_meal(m, req, tol)
        )
        return self._envelope("single_meal", meal, meta, checks.macro_warnings([meal]))

    def analyze(self, food_items: str) -> Envelope[NutritionAnalysis]:
        analysis, meta = self._generate(
            "analysis",
            prompts.analysis_prompt(food_items),
            NutritionAnalysis,
            checks.check_analysis,
        )
        return self._envelope("analysis", analysis, meta, checks.macro_warnings(analysis.items))

    def substitute(self, req: SubstituteRequest) -> Envelope[Substitutions]:
        excluded = req.excluded_foods
        subs, meta = self._generate(
            "substitution",
            prompts.substitute_prompt(req),
            Substitutions,
            lambda s: checks.check_substitutions(s, excluded),
        )
        return self._envelope("substitution", subs, meta)

    def tips(self, goal: str | None = None) -> Envelope[Tips]:
        tips, meta = self._generate("tips", prompts.tips_prompt(goal), Tips, checks.check_tips)
        return self._envelope("tips", tips, meta)

    # ------------------------------------------------------------
    # Shared machinery
    # ------------------------------------------------------------

    def _plan(self, kind: str, req: PlanRequest, prompt: tuple[str, str]) -> Envelope[WeeklyPlan]:
        tol = self.settings.calorie_tolerance
        plan, meta = self._generate(
            kind, prompt, WeeklyPlan, lambda p: checks.check_plan(p, req, tol)
        )
        plan.days.sort(key=lambda d: d.day)
        warnings = checks.macro_warnings(m for d in plan.days for m in d.meals)
        if req.diseases:
            warnings.insert(0, CONDITIONS_WARNING)
        return self._envelope(kind, plan, meta, warnings)

    def _generate(
        self, kind: str, prompt: tuple[str, str], schema: type[T], check: Check[T]
    ) -> tuple[T, Meta]:
        """Call the LLM, parse and check its JSON, and send failures back for repair."""
        system, user = prompt
        messages: list[Message] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        started = time.perf_counter()
        prompt_tokens = completion_tokens = 0

        for attempt in range(self.settings.max_repairs + 1):
            completion = self.llm.complete(messages)
            prompt_tokens += completion.prompt_tokens
            completion_tokens += completion.completion_tokens
            try:
                result = schema.model_validate_json(_FENCE.sub("", completion.content.strip()))
                problems = check(result)
            except ValidationError as exc:
                problems = _validation_problems(exc)

            if not problems:
                meta = Meta(
                    provider=self.llm.provider,
                    model=self.llm.model,
                    prompt_version=prompts.PROMPT_VERSION,
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    repairs=attempt,
                )
                logger.info(
                    "llm_ok kind=%s model=%s latency_ms=%d tokens=%d+%d repairs=%d",
                    kind,
                    meta.model,
                    meta.latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    attempt,
                )
                return result, meta

            logger.warning(
                "llm_check_failed kind=%s attempt=%d problems=%s", kind, attempt, problems
            )
            messages += [
                {"role": "assistant", "content": completion.content},
                {"role": "user", "content": prompts.repair_prompt(problems)},
            ]

        raise OutputValidationError(kind, problems)

    @staticmethod
    def _envelope(kind: str, data: T, meta: Meta, warnings: list[str] | None = None) -> Envelope[T]:
        return Envelope[type(data)](
            type=kind, data=data, warnings=warnings or [], meta=meta, disclaimer=DISCLAIMER
        )
