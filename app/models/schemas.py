from typing import Optional

from pydantic import BaseModel

# ============================================================
# Pydantic Models
# ============================================================

class UserData(BaseModel):
    meal_preference: str
    calories: int
    meal_count: int
    diseases: Optional[str] = None
    goal: str
    age: int
    dislikes: Optional[str] = None
    preferred_foods: Optional[str] = None


class FoodInput(BaseModel):
    food_items: str


class ModifyPlanInput(BaseModel):
    existing_plan: str
    modification_request: str