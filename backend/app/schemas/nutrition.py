from datetime import date

from pydantic import BaseModel, Field


class MealRead(BaseModel):
    meal: str = Field(description="breakfast, lunch, dinner, snack or unknown")
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


class NutritionDayRead(BaseModel):
    date: date
    source: str = Field(description="healthconnect or mfp_export")
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    sodium_mg: float | None
    meals: list[MealRead]


class NutritionWeekRead(BaseModel):
    week_start: date
    days_tracked: int
    kcal: float
    protein_g: float | None


class WeightRead(BaseModel):
    date: date
    kg: float
    source: str


class NutritionAverages(BaseModel):
    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None


class NutritionSummaryRead(BaseModel):
    since: date
    until: date
    days: list[NutritionDayRead] = Field(description="Tracked days only; untracked days are gaps")
    goals: dict[str, float]
    averages: NutritionAverages = Field(description="Over tracked days, today excluded")
    weeks: list[NutritionWeekRead]
    protein_goal_days: int | None
    weight: WeightRead | None
    weight_change: float | None = Field(description="kg from the first to the last weight in range")


class GoalUpdate(BaseModel):
    value: float = Field(gt=0, le=100000)
    valid_from: date | None = Field(None, description="Default today")


class GoalRead(BaseModel):
    metric: str
    value: float
    valid_from: date


class MfpImportResult(BaseModel):
    meals_created: int
    meals_updated: int
    meals_unchanged: int
    days: int
    weights: int
    weights_created: int
    first: date
    last: date
    ignored_files: list[str]
