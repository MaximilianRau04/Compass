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
    source: str = Field(
        description="healthconnect or an export: mfp_export, cronometer_export, loseit_export"
    )
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    sodium_mg: float | None
    saturated_fat_g: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None
    meals: list[MealRead]
    flags: list[str] = Field(
        default_factory=list, description="incomplete (under 1500 kcal), same_as_previous_day"
    )


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
    sodium_mg: float | None = None
    saturated_fat_g: float | None = None
    potassium_mg: float | None = None
    calcium_mg: float | None = None
    iron_mg: float | None = None


class NutritionQuality(BaseModel):
    incomplete: list[date] = Field(description="Logged under 1500 kcal")
    same_as_previous_day: list[date]
    gaps: list[date] = Field(description="Not logged at all")
    valid_days: int


class NutritionSummaryRead(BaseModel):
    since: date
    until: date
    days: list[NutritionDayRead] = Field(description="Tracked days only; untracked days are gaps")
    goals: dict[str, float]
    averages: NutritionAverages = Field(
        description="Over complete days without a quality flag, today excluded"
    )
    averages_all: NutritionAverages = Field(description="Over every complete logged day")
    quality: NutritionQuality
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


class NutritionImportResult(BaseModel):
    meals_created: int
    meals_updated: int
    meals_unchanged: int
    days: int
    weights: int
    weights_created: int
    first: date
    last: date
    ignored_files: list[str]
