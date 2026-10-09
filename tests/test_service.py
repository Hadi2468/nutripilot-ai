import pytest

from nutripilot.schemas import (
    MealRequest,
    PlanRequest,
    RegenerateRequest,
    SubstituteRequest,
    WeeklyPlan,
)
from nutripilot.service import NutriPilotService, OutputValidationError
from tests.conftest import PLAN_REQUEST, FakeLLM, meal, weekly_plan


@pytest.fixture
def req() -> PlanRequest:
    return PlanRequest(**PLAN_REQUEST)


def test_valid_plan_needs_one_call(settings, req):
    llm = FakeLLM(weekly_plan())
    result = NutriPilotService(llm, settings).plan(req)
    assert len(llm.calls) == 1 and result.meta.repairs == 0
    assert result.warnings == []


def test_failed_check_is_repaired_with_the_problems(settings, req):
    llm = FakeLLM(weekly_plan(kcal_per_meal=300), weekly_plan())  # 1200 kcal, then 2000
    result = NutriPilotService(llm, settings).plan(req)

    assert result.meta.repairs == 1
    assert result.meta.prompt_tokens == 200  # summed over both calls
    repair = llm.calls[1]
    assert [m["role"] for m in repair] == ["system", "user", "assistant", "user"]
    assert "Day 1 totals 1200 kcal but the target is 2000 kcal" in repair[-1]["content"]


def test_allergen_that_survives_repair_fails(settings, req):
    llm = FakeLLM(weekly_plan(ingredients=["peanut butter", "toast"]))
    with pytest.raises(OutputValidationError) as err:
        NutriPilotService(llm, settings).plan(req)
    assert len(llm.calls) == settings.max_repairs + 1
    assert "contains excluded food 'peanuts'" in err.value.problems[0]


def test_invalid_json_is_repaired(settings, req):
    llm = FakeLLM("Here is your plan: Day 1 ...", weekly_plan())
    result = NutriPilotService(llm, settings).plan(req)
    assert result.meta.repairs == 1
    assert "Invalid JSON" in llm.calls[1][-1]["content"]


def test_code_fences_are_tolerated(settings, req):
    import json

    llm = FakeLLM(f"```json\n{json.dumps(weekly_plan())}\n```")
    assert NutriPilotService(llm, settings).plan(req).meta.repairs == 0


def test_no_repairs_when_budget_is_zero(settings, req):
    llm = FakeLLM(weekly_plan(kcal_per_meal=300))
    with pytest.raises(OutputValidationError):
        NutriPilotService(llm, settings.model_copy(update={"max_repairs": 0})).plan(req)
    assert len(llm.calls) == 1


def test_days_are_sorted_and_conditions_add_a_warning(settings):
    plan = weekly_plan()
    plan["days"].reverse()
    req = PlanRequest(**PLAN_REQUEST, diseases="type 2 diabetes")
    llm = FakeLLM(plan)
    result = NutriPilotService(llm, settings).plan(req)

    assert [d.day for d in result.data.days] == list(range(1, 8))
    assert "not been reviewed by a clinician" in result.warnings[0]
    assert "type 2 diabetes" in llm.calls[0][1]["content"]


def test_macro_mismatch_is_a_warning_not_a_failure(settings):
    llm = FakeLLM(meal(calories=900))  # macros add up to ~502 kcal
    result = NutriPilotService(llm, settings).meal(MealRequest(calories=900))
    assert result.meta.repairs == 0
    assert "macronutrients add up to ~502 kcal" in result.warnings[0]


def test_regenerate_holds_the_revision_to_the_profile(settings, req):
    existing = WeeklyPlan.model_validate(weekly_plan())
    llm = FakeLLM(weekly_plan(meals_per_day=3), weekly_plan())
    result = NutriPilotService(llm, settings).regenerate(
        RegenerateRequest(profile=req, existing_plan=existing, modification_request="Less rice")
    )
    assert result.type == "modified_plan" and result.meta.repairs == 1
    prompt = llm.calls[0][1]["content"]
    assert "Requested change: Less rice" in prompt and '"totals"' not in prompt


def test_substitution_with_excluded_food_is_repaired(settings):
    bad = {
        "substitutions": [{"original": "chips", "alternative": "roasted peanuts", "why": "Protein"}]
    }
    good = {
        "substitutions": [
            {"original": "chips", "alternative": "air-popped popcorn", "why": "Fibre"}
        ]
    }
    llm = FakeLLM(bad, good)
    result = NutriPilotService(llm, settings).substitute(
        SubstituteRequest(food_items="chips", allergies="peanuts")
    )
    assert result.data.substitutions[0].alternative == "air-popped popcorn"


def test_tips_must_be_exactly_five(settings):
    llm = FakeLLM(
        {"tips": [{"tip": "t", "why": "w"}] * 3}, {"tips": [{"tip": "t", "why": "w"}] * 5}
    )
    assert NutriPilotService(llm, settings).tips().meta.repairs == 1
