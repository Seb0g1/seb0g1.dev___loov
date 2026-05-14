from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.migrations import ensure_project_schema
from app.db.session import engine
from app.models import entities  # noqa: F401
from app.db.session import SessionLocal
from app.services.seed import seed_defaults
from app.workers.scheduler import start_scheduler, stop_scheduler


settings = get_settings()
configure_logging(settings.debug)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)


@app.on_event("startup")
async def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_project_schema(engine)
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    ensure_project_schema(engine)
    start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    stop_scheduler()
