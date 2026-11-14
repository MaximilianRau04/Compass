from fastapi import APIRouter

from app.api import (
    areas,
    body,
    calendar,
    correlations,
    feeds,
    finance,
    habits,
    health,
    ingest,
    journal,
    mail,
    news,
    notes,
    nutrition,
    push,
    search,
    setup,
    sleep,
    tasks,
    training,
)

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(setup.router)
router.include_router(areas.router)
router.include_router(tasks.router)
router.include_router(calendar.router)
router.include_router(feeds.router)
router.include_router(training.router)
router.include_router(sleep.router)
router.include_router(nutrition.router)
router.include_router(body.router)
router.include_router(finance.router)
router.include_router(mail.router)
router.include_router(news.router)
router.include_router(notes.router)
router.include_router(journal.router)
router.include_router(habits.router)
router.include_router(correlations.router)
router.include_router(search.router)
router.include_router(push.router)
router.include_router(ingest.router)
