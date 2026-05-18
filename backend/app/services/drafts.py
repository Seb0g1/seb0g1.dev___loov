from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DraftPost, GenerationLog, Product, Project
from app.services.generation.image import render_poster
from app.services.generation.text import generate_text
from app.services.live_product import refresh_product_live_data
from app.services.marketplace_links import normalize_marketplace


def product_to_payload(product: Product) -> dict:
    return {
        "id": product.id,
        "source": product.source,
        "source_id": product.source_id,
        "title": product.title,
        "brand": product.brand,
        "category": product.category,
        "price": product.price,
        "market_price": product.market_price,
        "discount_percent": product.discount_percent,
        "rating": product.rating,
        "reviews_count": product.reviews_count,
        "stock_count": product.stock_count,
        "url": product.url,
        "affiliate_url": product.affiliate_url,
        "description": product.description,
        "characteristics": json.loads(product.characteristics_json or "{}"),
        "images": [image.url for image in product.images],
    }


def project_to_payload(project: Project | None) -> dict | None:
    if not project:
        return None
    return {
        "id": project.id,
        "slug": project.slug,
        "name": project.name,
        "telegram_channel_url": project.telegram_channel_url,
        "telegram_channel_id": project.telegram_channel_id,
        "niche": project.niche,
        "description": project.description,
        "tagline": project.tagline,
        "accent_color": project.accent_color,
        "accent_secondary": project.accent_secondary,
        "logo_text": project.logo_text,
        "category_focus_json": project.category_focus_json,
    }


def _live_price_verified(product: Product) -> bool:
    try:
        data = json.loads(product.characteristics_json or "{}")
        return bool(data.get("live_price_verified"))
    except Exception:
        return False


def _ensure_live_price(product: Product) -> None:
    if normalize_marketplace(product.source) == "yandex_market" and not _live_price_verified(product):
        raise RuntimeError("Не удалось подтвердить актуальную цену товара на Яндекс Маркете")


def pick_next_product_for_project(db: Session, project_id: int, exclude_product_id: int | None = None) -> Product | None:
    candidates = db.scalars(
        select(Product)
        .where(
            Product.project_id == project_id,
            Product.is_active.is_(True),
            Product.is_excluded.is_(False),
            Product.is_published.is_(False),
        )
        .order_by(Product.score.desc(), Product.created_at.desc())
        .limit(100)
    ).all()
    drafted_ids = {
        row[0]
        for row in db.execute(
            select(DraftPost.product_id).where(
                DraftPost.project_id == project_id,
                DraftPost.product_id.is_not(None),
            )
        ).all()
        if row[0] is not None
    }
    for product in candidates:
        if exclude_product_id and product.id == exclude_product_id:
            continue
        if product.id in drafted_ids:
            continue
        return product
    return None


async def create_draft_from_product(db: Session, product: Product, style: str = "short", notify_admin: bool = True) -> DraftPost:
    await refresh_product_live_data(db, product)
    _ensure_live_price(product)
    payload = product_to_payload(product)
    project_payload_data = project_to_payload(product.project)
    text_result = await generate_text(payload, style=style, project=project_payload_data)
    db.add(
        GenerationLog(
            project_id=product.project_id,
            product_id=product.id,
            kind="text",
            provider=text_result.provider,
            prompt=text_result.prompt,
            result=text_result.text,
        )
    )
    image_path = await render_poster(payload, project=project_payload_data, output_name=f"product_{product.id}_{style}.png")
    db.add(
        GenerationLog(
            project_id=product.project_id,
            product_id=product.id,
            kind="image",
            provider="pillow-local",
            prompt=f"poster:{style}",
            result=image_path,
        )
    )
    draft = DraftPost(
        project_id=product.project_id,
        product_id=product.id,
        title=product.title,
        text=text_result.text,
        style=style,
        image_path=image_path,
        status="review",
    )
    db.add(draft)
    db.flush()
    product.is_active = True
    db.commit()
    db.refresh(draft)
    if notify_admin:
        try:
            from app.services.review import send_draft_for_review

            await send_draft_for_review(db, draft)
        except Exception:
            pass
    return draft


async def regenerate_draft(db: Session, draft: DraftPost, regenerate_text: bool = True, regenerate_image: bool = True, notify_admin: bool = True) -> DraftPost:
    product = db.get(Product, draft.product_id) if draft.product_id else None
    if not product:
        return draft
    await refresh_product_live_data(db, product)
    _ensure_live_price(product)
    payload = product_to_payload(product)
    project_payload_data = project_to_payload(product.project)
    if regenerate_text:
        text_result = await generate_text(payload, style=draft.style, project=project_payload_data)
        draft.text = text_result.text
        db.add(
            GenerationLog(
                project_id=draft.project_id,
                product_id=product.id,
                draft_id=draft.id,
                kind="text",
                provider=text_result.provider,
                prompt=text_result.prompt,
                result=text_result.text,
            )
        )
    if regenerate_image:
        draft.image_path = await render_poster(payload, project=project_payload_data, output_name=f"draft_{draft.id}_{datetime.utcnow().timestamp():.0f}.png")
        db.add(
            GenerationLog(
                project_id=draft.project_id,
                product_id=product.id,
                draft_id=draft.id,
                kind="image",
                provider="pillow-local",
                prompt=f"draft:{draft.id}:{draft.style}",
                result=draft.image_path,
            )
        )
    draft.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(draft)
    if notify_admin:
        try:
            from app.services.review import send_draft_for_review

            await send_draft_for_review(db, draft)
        except Exception:
            pass
    return draft
