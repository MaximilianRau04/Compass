from fastapi import APIRouter

from app.api import areas, health, tasks

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(areas.router)
router.include_router(tasks.router)
