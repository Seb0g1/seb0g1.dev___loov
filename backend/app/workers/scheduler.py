from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import AdRequest, DraftPost, Product, Project, ScheduleItem
from app.services.advertising import delete_expired_ad_posts
from app.services.drafts import create_draft_from_product, pick_next_product_for_project
from app.services.importer import import_products
from app.services.publishing import publish_draft
from app.services.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_import_job() -> None:
    db = SessionLocal()
    try:
        projects = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.sort_order.asc(), Project.id.asc())).all()
        for project in projects:
            import_products(db, project)
            pending_review = db.scalar(
                select(DraftPost.id).where(
                    DraftPost.project_id == project.id,
                    DraftPost.status.in_(["review", "approved", "scheduled"]),
                ).limit(1)
            )
            if pending_review:
                continue
            next_product = pick_next_product_for_project(db, project.id)
            if next_product:
                await create_draft_from_product(db, next_product)
    finally:
        db.close()


async def run_publish_job() -> None:
    settings = load_runtime_config()
    if not settings.auto_posting_enabled:
        return
    db = SessionLocal()
    try:
        pending = db.scalars(
            select(ScheduleItem)
            .where(ScheduleItem.status == "pending", ScheduleItem.run_at <= datetime.utcnow())
            .order_by(ScheduleItem.run_at.asc())
            .limit(10)
        ).all()
        for item in pending:
            draft = db.get(DraftPost, item.draft_id) if item.draft_id else None
            if not draft:
                item.status = "failed"
                item.last_error = "Draft missing"
                continue
            try:
                await publish_draft(db, draft)
                item.status = "published"
                item.last_error = None
            except Exception as exc:
                logger.exception("Publish failed: %s", exc)
                item.status = "failed"
                item.last_error = str(exc)
        db.commit()
    finally:
        db.close()


async def run_ad_cleanup_job() -> None:
    db = SessionLocal()
    try:
        await delete_expired_ad_posts(db)
    finally:
        db.close()


def start_scheduler() -> None:
    settings = load_runtime_config()
    if scheduler.running:
        return
    scheduler.add_job(run_import_job, "interval", minutes=max(settings.import_interval_minutes, 5), id="import_products", replace_existing=True)
    scheduler.add_job(run_publish_job, "interval", minutes=max(settings.publish_interval_minutes, 1), id="publish_queue", replace_existing=True)
    scheduler.add_job(run_ad_cleanup_job, "interval", minutes=10, id="ad_cleanup", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def restart_scheduler() -> None:
    if scheduler.running:
        scheduler.remove_all_jobs()
        scheduler.shutdown(wait=False)
    start_scheduler()
