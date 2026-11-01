from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.api.deps import SessionDep
from app.ingestion import nutrition_export
from app.models.nutrition import Goal
from app.schemas.nutrition import (
    GoalRead,
    GoalUpdate,
    NutritionAverages,
    NutritionDayRead,
    NutritionImportResult,
    NutritionQuality,
    NutritionSummaryRead,
    NutritionWeekRead,
    WeightRead,
)
from app.services import nutrition
from app.services.nutrition import NutritionError

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

Metric = Annotated[
    str,
    Path(pattern="^(kcal|protein_g|carbs_g|fat_g|steps|hr_max|weight_loss_min|weight_loss_max)$"),
]


@router.get("/summary", response_model=NutritionSummaryRead)
def summary(session: SessionDep, days: Annotated[int, Query(ge=1, le=366)] = 30):
    s = nutrition.summary(session, days)
    return NutritionSummaryRead(
        since=s.since,
        until=s.until,
        days=[NutritionDayRead.model_validate(d, from_attributes=True) for d in s.days],
        goals=s.goals,
        averages=NutritionAverages(**s.averages),
        averages_all=NutritionAverages(**s.averages_all),
        quality=NutritionQuality(**s.quality.__dict__),
        weeks=[NutritionWeekRead(**w.__dict__) for w in s.weeks],
        protein_goal_days=s.protein_goal_days,
        weight=WeightRead(**s.weight.__dict__) if s.weight else None,
        weight_change=s.weight_change,
    )


@router.get("/weight", response_model=list[WeightRead])
def weight(session: SessionDep):
    """All weights, one per day, oldest first."""
    return [WeightRead(**w.__dict__) for w in nutrition.weights(session)]


@router.get("/goals", response_model=list[GoalRead])
def goals(session: SessionDep):
    """Every goal ever set, newest first per metric."""
    rows = session.scalars(select(Goal).order_by(Goal.metric, Goal.valid_from.desc()))
    return [GoalRead(metric=g.metric, value=float(g.value), valid_from=g.valid_from) for g in rows]


@router.put("/goals/{metric}", response_model=GoalRead)
def set_goal(metric: Metric, data: GoalUpdate, session: SessionDep):
    try:
        goal = nutrition.set_goal(session, metric, data.value, data.valid_from)
    except NutritionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return GoalRead(metric=goal.metric, value=float(goal.value), valid_from=goal.valid_from)


@router.post("/import", response_model=NutritionImportResult)
async def import_nutrition(request: Request, session: SessionDep):
    """Import the export of a nutrition app: a zip or one of its CSV files, as the raw request
    body."""
    if int(request.headers.get("content-length") or 0) > nutrition_export.MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file is larger than 10 MB")
    data = await request.body()

    def run() -> dict:
        result = nutrition_export.import_export(session, data)
        session.commit()
        return result

    try:
        return await run_in_threadpool(run)
    except nutrition_export.NutritionImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
