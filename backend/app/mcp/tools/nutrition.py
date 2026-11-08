"""Tools for nutrition, body measurements and the weekly review."""

from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.mcp.core import IDEMPOTENT_WRITE, READ, mcp
from app.mcp.db import session_scope
from app.mcp.guards import audited
from app.mcp.schemas import (
    BodyTrendOut,
    GoalOut,
    NutritionDayOut,
    NutritionQualityOut,
    NutritionSummaryOut,
    RecommendationOut,
    WeeklyReviewOut,
    body_out,
)
from app.services import body, nutrition, review


@mcp.tool(title="Nutrition", annotations=READ)
def nutrition_summary(
    days: Annotated[int, Field(ge=1, le=90, description="How many days back")] = 7,
) -> NutritionSummaryOut:
    """Calories and macros per day and meal (logged in a nutrition app), daily goals, averages and
    the body weight trend. Days the user did not log are missing, not 0 kcal; today is still
    running."""
    with session_scope() as session:
        s = nutrition.summary(session, days)
        return NutritionSummaryOut(
            since=s.since,
            until=s.until,
            goals=s.goals,
            averages=s.averages,
            averages_all_logged_days=s.averages_all,
            quality=NutritionQualityOut(
                incomplete_days=s.quality.incomplete,
                same_as_previous_day=s.quality.same_as_previous_day,
                gap_days=s.quality.gaps,
                valid_days=s.quality.valid_days,
            ),
            protein_goal_days=s.protein_goal_days,
            days=[
                NutritionDayOut(
                    date=d.date,
                    kcal=d.kcal,
                    protein_g=d.protein_g,
                    carbs_g=d.carbs_g,
                    fat_g=d.fat_g,
                    fiber_g=d.fiber_g,
                    sugar_g=d.sugar_g,
                    saturated_fat_g=d.saturated_fat_g,
                    sodium_mg=d.sodium_mg,
                    potassium_mg=d.potassium_mg,
                    calcium_mg=d.calcium_mg,
                    iron_mg=d.iron_mg,
                    meals_kcal={m.meal: m.kcal for m in d.meals},
                    flags=d.flags,
                )
                for d in s.days
            ],
            weight_kg=s.weight.kg if s.weight else None,
            weight_date=s.weight.date if s.weight else None,
            weight_change_kg=s.weight_change,
        )


@mcp.tool(title="Set nutrition goal", annotations=IDEMPOTENT_WRITE)
def set_nutrition_goal(
    metric: Literal[
        "kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "steps",
        "hr_max",
        "weight_loss_min",
        "weight_loss_max",
    ],
    value: Annotated[
        float,
        Field(
            gt=0,
            le=100000,
            description="Per day (kcal, grams, steps); hr_max in bpm; weight loss in kg per week",
        ),
    ],
    valid_from: Annotated[date | None, Field(description="YYYY-MM-DD, default today")] = None,
) -> GoalOut:
    """Set a goal: daily kcal, protein, carbs, fat or steps, the maximum heart rate (for zone 2)
    or the target weight loss per week (min and max). It applies from valid_from until a newer
    goal replaces it; earlier days keep their old goal."""
    with audited("set_nutrition_goal", locals()) as session:
        goal = nutrition.set_goal(session, metric, value, valid_from)
        return GoalOut(metric=goal.metric, value=float(goal.value), valid_from=goal.valid_from)


@mcp.tool(title="Body trend", annotations=READ)
def body_trend(
    weeks: Annotated[int, Field(ge=2, le=52, description="How many weeks back")] = 8,
) -> BodyTrendOut:
    """Body weight as 7-day means (morning weigh-ins: manual, Health Connect or an export, one per
    day), the weekly change in kg and percent against the target loss rate, and the waist."""
    with session_scope() as session:
        return body_out(body.trend(session, weeks))


@mcp.tool(title="Log body metric", annotations=IDEMPOTENT_WRITE)
def log_body_metric(
    metric: Literal["weight", "waist"],
    value: Annotated[float, Field(description="kg for weight (morning), cm for waist")],
    day: Annotated[date | None, Field(description="YYYY-MM-DD, default today")] = None,
) -> BodyTrendOut:
    """Store the user's morning weight or waist circumference for a day, as the user said.
    Entering the same metric for the same day again replaces it."""
    with audited("log_body_metric", {"metric": metric, "value": value, "day": day}) as session:
        try:
            body.log(session, metric, value, day)
        except body.BodyError as exc:
            raise ToolError(str(exc)) from exc
        return body_out(body.trend(session))


@mcp.tool(title="Weekly review", annotations=READ)
def weekly_review() -> WeeklyReviewOut:
    """The last 7 days in numbers: average kcal, protein and fat (valid days only), weight trend
    and waist, median steps, training sessions, progress and stagnation, strength trend, sleep
    duration and consistency, resting heart rate, zone 2 minutes; plus a calorie recommendation
    by fixed rules if the user has set a weight loss goal. Compass saves it itself every Sunday
    as the brief of kind "weekly"."""
    with session_scope() as session:
        r = review.weekly_review(session)
        numbers = {
            k: v for k, v in r.__dict__.items() if k not in ("since", "until", "recommendation")
        }
        return WeeklyReviewOut(
            since=r.since,
            until=r.until,
            numbers=numbers,
            recommendation=RecommendationOut(**r.recommendation.__dict__),
            rules=(
                f"Loss under {review.SLOW_LOSS} kg/week for 2 weeks with the waist unchanged: "
                f"-{review.KCAL_STEP} kcal. Loss over {review.FAST_LOSS} kg/week or strength "
                f"down more than {review.STRENGTH_DROP} %: +{review.KCAL_STEP} kcal. "
                "Otherwise keep."
            ),
            markdown=review.markdown(r),
        )
