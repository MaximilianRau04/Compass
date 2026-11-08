from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.models.tasks import Area
from app.schemas.tasks import AreaCreate, AreaRead, AreaUpdate
from app.services import tasks as task_service

router = APIRouter(prefix="/areas", tags=["areas"])


@router.get("", response_model=list[AreaRead])
def list_areas(session: SessionDep, include_archived: bool = False):
    return task_service.list_areas(session, include_archived)


@router.post("", response_model=AreaRead, status_code=status.HTTP_201_CREATED)
def create_area(data: AreaCreate, session: SessionDep):
    if task_service.find_area(session, data.slug):
        raise HTTPException(status.HTTP_409_CONFLICT, f"area '{data.slug}' already exists")
    area = Area(**data.model_dump())
    session.add(area)
    session.commit()
    return area


@router.patch("/{area_id}", response_model=AreaRead)
def update_area(area_id: int, data: AreaUpdate, session: SessionDep):
    area = session.get(Area, area_id)
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "area not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(area, field, value)
    session.commit()
    return area
