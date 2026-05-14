from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import DraftPost, Product, PublishedPost


def build_analytics(db: Session, project_id: int | None = None) -> dict:
    product_query = select(Product).where(Product.project_id == project_id) if project_id is not None else select(Product)
    draft_query = select(DraftPost).where(DraftPost.project_id == project_id) if project_id is not None else select(DraftPost)
    published_query = select(PublishedPost).where(PublishedPost.project_id == project_id) if project_id is not None else select(PublishedPost)

    products_total = db.scalar(select(func.count()).select_from(product_query.subquery())) or 0
    products_active = db.scalar(select(func.count()).select_from(product_query.where(Product.is_active.is_(True)).subquery())) or 0
    products_excluded = db.scalar(select(func.count()).select_from(product_query.where(Product.is_excluded.is_(True)).subquery())) or 0
    drafts_total = db.scalar(select(func.count()).select_from(draft_query.subquery())) or 0
    drafts_pending = db.scalar(select(func.count()).select_from(draft_query.where(DraftPost.status.in_(["draft", "review", "approved", "scheduled"])).subquery())) or 0
    published_total = db.scalar(select(func.count()).select_from(published_query.subquery())) or 0
    average_score = db.scalar(select(func.avg(Product.score)).where(Product.project_id == project_id)) if project_id is not None else db.scalar(select(func.avg(Product.score)))
    average_score = average_score or 0
    by_source_rows = db.execute((select(Product.source, func.count()).where(Product.project_id == project_id) if project_id is not None else select(Product.source, func.count())).group_by(Product.source)).all()
    by_status_rows = db.execute((select(DraftPost.status, func.count()).where(DraftPost.project_id == project_id) if project_id is not None else select(DraftPost.status, func.count())).group_by(DraftPost.status)).all()
    return {
        "products_total": int(products_total),
        "products_active": int(products_active),
        "products_excluded": int(products_excluded),
        "drafts_total": int(drafts_total),
        "drafts_pending": int(drafts_pending),
        "published_total": int(published_total),
        "average_score": round(float(average_score or 0), 2),
        "by_source": {source: count for source, count in by_source_rows},
        "by_status": {status: count for status, count in by_status_rows},
    }
