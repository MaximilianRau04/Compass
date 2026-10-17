from fastapi import APIRouter

from app.api import areas, calendar, health, tasks, training

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(areas.router)
router.include_router(tasks.router)
router.include_router(calendar.router)
router.include_router(training.router)
