"""Audience and safety guidance injected into prompts. The hard rules (age/goal and calorie
bounds, excluded foods) are enforced in code by `schemas.py` and `checks.py`."""

from __future__ import annotations

DISCLAIMER = (
    "AI-generated nutrition information for general wellness only; not medical advice. "
    "Consult a doctor or registered dietitian for medical conditions, pregnancy, "
    "allergies or eating disorders."
)

CONDITIONS_WARNING = (
    "This plan was adjusted for the stated health conditions but has not been reviewed by "
    "a clinician. Check it with your doctor or dietitian before following it."
)


def audience_guidance(age: int | None) -> str:
    if age is None:
        return "Write for an adult."
    if age < 13:
        return (
            "Write for the parent or caregiver of a child. Never suggest dieting, calorie "
            "restriction or weight loss; focus on balanced family meals and growth."
        )
    if age < 18:
        return (
            "Write for a teenager and their family. Never suggest weight-loss diets or calorie "
            "restriction; support growth, sports and a positive relationship with food."
        )
    if age >= 65:
        return (
            "Write for an older adult. Prioritise protein at every meal, hydration, calcium, "
            "vitamin D and fibre; avoid aggressive calorie deficits."
        )
    return "Write for an adult."


def conditions_guidance(diseases: str | None) -> str:
    if not diseases:
        return "No health conditions were stated."
    return (
        f"Stated health conditions: {diseases}. Choose foods that suit them using widely "
        "accepted dietary guidance. Never suggest changing medication, never claim the "
        "plan treats or cures a condition."
    )
