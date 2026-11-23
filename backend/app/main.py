import logging

from fastapi import FastAPI

from app.api import router
from app.body_limit import BodyLimit
from app.config import get_settings
from app.proxy_auth import ProxySecret

logging.basicConfig(level=get_settings().log_level)

app = FastAPI(title="Compass", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(router)
app.add_middleware(ProxySecret)
app.add_middleware(BodyLimit)
