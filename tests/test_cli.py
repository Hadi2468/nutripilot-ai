import json

import pytest

from nutripilot.cli import main
from nutripilot.service import NutriPilotService
from tests.conftest import FakeLLM, meal, weekly_plan

ITEM = {
    "food": "rice",
    "quantity": "1 cup",
    "calories": 200,
    "protein_g": 4,
    "carbs_g": 44,
    "fat_g": 0.4,
}
TIPS = {"tips": [{"tip": f"Tip {i}", "why": "Because"} for i in range(5)]}
SUBS = {
    "substitutions": [{"original": "soda", "alternative": "sparkling water", "why": "No sugar"}]
}


@pytest.mark.parametrize(
    ("argv", "reply", "expected"),
    [
        (
            ["plan", "--calories", "2000", "--meals", "4", "--allergies", "peanuts"],
            weekly_plan(),
            "Day 7",
        ),
        (["meal", "--calories", "500", "--type", "dinner"], meal(), "red lentils"),
        (["analyze", "1 cup rice"], {"items": [ITEM]}, "Total"),
        (["substitute", "soda"], SUBS, "sparkling water"),
        (["tips", "--goal", "muscle gain"], TIPS, "Tip 4"),
    ],
)
def test_commands_render(settings, capsys, argv, reply, expected):
    assert main(argv, NutriPilotService(FakeLLM(reply), settings)) == 0
    out = " ".join(capsys.readouterr().out.split())  # undo rich line wrapping
    assert expected in out and "not medical advice" in out


def test_json_output(settings, capsys):
    assert main(["--json", "tips"], NutriPilotService(FakeLLM(TIPS), settings)) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "tips"


def test_invalid_input_exits_2(settings, capsys):
    service = NutriPilotService(FakeLLM(), settings)
    assert main(["plan", "--age", "12", "--goal", "weight loss"], service) == 2
    assert "under-18s" in capsys.readouterr().out


def test_failed_output_exits_1(settings, capsys):
    service = NutriPilotService(FakeLLM({"tips": []}), settings)
    assert main(["tips"], service) == 1
    assert "exactly 5 tips" in capsys.readouterr().out
