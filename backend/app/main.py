import logging

from fastapi import FastAPI

from app.api import router
from app.config import get_settings

logging.basicConfig(level=get_settings().log_level)

app = FastAPI(title="Compass", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(router)
