from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import SessionDep
from app.models.tasks import Task, TaskStatus
from app.schemas.tasks import (
    QuickAddPreview,
    QuickAddRequest,
    TaskCreate,
    TaskEventRead,
    TaskMove,
    TaskRead,
    TaskUpdate,
    TodayOverview,
)
from app.services import tasks as task_service
from app.services.tasks import TaskError

router = APIRouter(tags=["tasks"])


def _get(session, task_id: int) -> Task:
    task = task_service.get_task(session, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return task


def _bad_request(exc: TaskError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("/today", response_model=TodayOverview)
def today(session: SessionDep):
    return task_service.today_overview(session)


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    session: SessionDep,
    status_: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    area_id: int | None = None,
    q: str | None = None,
):
    return task_service.list_tasks(session, status=status_, area_id=area_id, query=q)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, session: SessionDep):
    try:
        task = task_service.create_task(session, data)
    except TaskError as exc:
        raise _bad_request(exc) from exc
    session.commit()
    return task


@router.post("/tasks/quick", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def quick_add(data: QuickAddRequest, session: SessionDep):
    try:
        task = task_service.quick_add(session, data.text)
    except TaskError as exc:
        raise _bad_request(exc) from exc
    session.commit()
    return task


@router.post("/tasks/quick/preview", response_model=QuickAddPreview)
def quick_add_preview(data: QuickAddRequest, session: SessionDep):
    return task_service.preview_quick_add(session, data.text)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: SessionDep):
    return _get(session, task_id)


@router.get("/tasks/{task_id}/events", response_model=list[TaskEventRead])
def task_events(task_id: int, session: SessionDep):
    return _get(session, task_id).events


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(task_id: int, data: TaskUpdate, session: SessionDep):
    task = _get(session, task_id)
    try:
        task_service.update_task(session, task, data)
    except TaskError as exc:
        raise _bad_request(exc) from exc
    session.commit()
    return task


@router.post("/tasks/{task_id}/move", response_model=TaskRead)
def move_task(task_id: int, data: TaskMove, session: SessionDep):
    """Plan the task for another day; an earlier deadline of your own moves along."""
    task = task_service.move_to(session, _get(session, task_id), data.date)
    session.commit()
    return task


@router.post("/tasks/{task_id}/complete", response_model=TaskRead)
def complete_task(task_id: int, session: SessionDep):
    task = task_service.set_status(session, _get(session, task_id), TaskStatus.done)
    session.commit()
    return task


@router.post("/tasks/{task_id}/reopen", response_model=TaskRead)
def reopen_task(task_id: int, session: SessionDep):
    task = task_service.set_status(session, _get(session, task_id), TaskStatus.open)
    session.commit()
    return task
