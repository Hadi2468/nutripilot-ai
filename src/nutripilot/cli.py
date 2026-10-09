"""`nutripilot` command: run any feature from the terminal through the same service as the API.

nutripilot plan --calories 2000 --meals 4 --goal "weight loss" --age 45 --allergies peanuts
nutripilot meal --calories 600 --type dinner
nutripilot analyze "2 eggs, 1 slice whole-grain toast, 1 banana"
nutripilot substitute "white rice, soda" --goal "weight loss"
nutripilot tips --json
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import get_args

from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.table import Table

from nutripilot.config import MODEL_CATALOG, get_settings, provider_of
from nutripilot.llm import LLMError, build_chat_model
from nutripilot.schemas import (
    Envelope,
    Goal,
    Macros,
    MealRequest,
    MealType,
    PlanRequest,
    SubstituteRequest,
)
from nutripilot.service import NutriPilotService, OutputValidationError

console = Console()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nutripilot", description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true", help="print the raw JSON response")
    parser.add_argument("--provider", choices=list(MODEL_CATALOG), help="LLM provider")
    parser.add_argument(
        "--model", help="model ID, e.g. claude-haiku-5-5 (default: the provider's default)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def restrictions(p: argparse.ArgumentParser) -> None:
        p.add_argument("--allergies", help="comma-separated, e.g. 'peanuts, shellfish'")
        p.add_argument("--dislikes", help="comma-separated")

    plan = sub.add_parser("plan", help="seven-day meal plan")
    plan.add_argument("--calories", type=int, default=2000)
    plan.add_argument("--meals", type=int, default=3, dest="meal_count")
    plan.add_argument("--goal", choices=get_args(Goal), default="healthy eating")
    plan.add_argument("--age", type=int, default=35)
    plan.add_argument("--preference", default="any", dest="meal_preference")
    plan.add_argument("--conditions", dest="diseases", help="health conditions to respect")
    plan.add_argument("--preferred-foods")
    restrictions(plan)

    meal = sub.add_parser("meal", help="one meal for a calorie target")
    meal.add_argument("--calories", type=int, default=600)
    meal.add_argument("--type", choices=get_args(MealType), default="lunch", dest="meal_type")
    meal.add_argument("--goal", choices=get_args(Goal), default="healthy eating")
    meal.add_argument("--preference", default="any", dest="meal_preference")
    restrictions(meal)

    analyze = sub.add_parser("analyze", help="nutrients of the foods you list")
    analyze.add_argument("food_items")

    substitute = sub.add_parser("substitute", help="healthier swaps")
    substitute.add_argument("food_items")
    substitute.add_argument("--goal", choices=get_args(Goal), default="healthy eating")
    restrictions(substitute)

    tips = sub.add_parser("tips", help="five healthy eating tips")
    tips.add_argument("--goal", choices=get_args(Goal))
    return parser


def _fields(args: argparse.Namespace, model: type[BaseModel]) -> dict:
    return {k: v for k, v in vars(args).items() if k in model.model_fields and v is not None}


def run(args: argparse.Namespace, service: NutriPilotService) -> Envelope:
    match args.command:
        case "plan":
            return service.plan(PlanRequest(**_fields(args, PlanRequest)))
        case "meal":
            return service.meal(MealRequest(**_fields(args, MealRequest)))
        case "analyze":
            return service.analyze(args.food_items)
        case "substitute":
            return service.substitute(SubstituteRequest(**_fields(args, SubstituteRequest)))
        case _:
            return service.tips(args.goal)


# ============================================================
# Rendering
# ============================================================


def _macros(m: Macros) -> list[str]:
    return [f"{m.calories:.0f}", f"{m.protein_g:.0f}", f"{m.carbs_g:.0f}", f"{m.fat_g:.0f}"]


def _table(title: str, first: str, rows: list[tuple[str, Macros]], total: Macros | None) -> Table:
    table = Table(title=title, title_justify="left")
    table.add_column(first)
    for col in ("kcal", "protein g", "carbs g", "fat g"):
        table.add_column(col, justify="right")
    for label, m in rows:
        table.add_row(label, *_macros(m))
    if total:
        table.add_row("[bold]Total[/bold]", *(f"[bold]{v}[/bold]" for v in _macros(total)))
    return table


def render(result: Envelope) -> None:
    data = result.data
    match result.type:
        case "weekly_plan" | "modified_plan":
            for day in data.days:
                rows = [(f"{m.name}: {m.dish}", m) for m in day.meals]
                console.print(_table(f"Day {day.day}", "Meal", rows, day.totals))
            for note in data.notes:
                console.print(f"• {note}")
        case "single_meal":
            console.print(_table(data.name, "Dish", [(data.dish, data)], None))
            console.print("Ingredients: " + ", ".join(data.ingredients))
        case "analysis":
            rows = [(f"{i.food} ({i.quantity})", i) for i in data.items]
            console.print(_table("Nutrition analysis", "Food", rows, data.totals))
        case "substitution":
            for s in data.substitutions:
                console.print(f"• [bold]{s.original}[/bold] → {s.alternative}: {s.why}")
        case _:
            for t in data.tips:
                console.print(f"• [bold]{t.tip}[/bold] {t.why}")

    for warning in result.warnings:
        console.print(f"[yellow]⚠ {warning}[/yellow]")
    m = result.meta
    console.print(
        f"[dim]{m.provider}/{m.model} · {m.latency_ms} ms · "
        f"{m.prompt_tokens}+{m.completion_tokens} tokens · repairs {m.repairs}[/dim]"
    )
    console.print(f"[dim]{result.disclaimer}[/dim]")


def main(argv: list[str] | None = None, service: NutriPilotService | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        if service is None:
            settings = get_settings()
            provider = args.provider or (args.model and provider_of(args.model)) or None
            service = NutriPilotService(build_chat_model(settings, provider, args.model), settings)
        with console.status("Asking the nutrition model..."):
            result = run(args, service)
    except ValidationError as exc:
        console.print(f"[red]Invalid input:[/red] {exc.errors()[0]['msg']}")
        return 2
    except (LLMError, OutputValidationError) as exc:
        console.print(f"[red]Error:[/red] {exc}")
        return 1

    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        render(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
