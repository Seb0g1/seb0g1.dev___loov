from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DraftPost, Product, PublishedPost, PublishLog
from app.services.live_product import refresh_product_live_data
from app.services.marketplace_links import build_marketplace_buttons, build_marketplace_footer, normalize_marketplace
from app.services.runtime_config import load_runtime_config
from app.services.telegram import TelegramPublisher


def build_cta_button(url: str | None) -> list[dict]:
    if not url:
        return []
    return [{"text": "Купить", "url": url}]


def build_cta_buttons(product: Product | None) -> list[dict]:
    if not product:
        return []
    buttons = build_marketplace_buttons(product)
    return buttons or build_cta_button(product.url)


def build_publish_caption(text: str, product: Product | None) -> str:
    if not product:
        return text
    footer = build_marketplace_footer(product)
    marker = "<b>Актуальная цена:</b>"
    body = text.split(marker, 1)[0].rstrip() if marker in text else text.rstrip()
    return f"{body}\n\n{footer}"


def _live_price_verified(product: Product) -> bool:
    try:
        data = json.loads(product.characteristics_json or "{}")
        return bool(data.get("live_price_verified"))
    except Exception:
        return False


async def publish_draft(db: Session, draft: DraftPost) -> PublishedPost:
    product = db.get(Product, draft.product_id) if draft.product_id else None
    if product:
        await refresh_product_live_data(db, product)
        if normalize_marketplace(product.source) == "yandex_market" and not _live_price_verified(product):
            raise RuntimeError("Не удалось подтвердить актуальную цену товара на Яндекс Маркете")
    existing = db.scalar(select(PublishedPost).where(PublishedPost.draft_id == draft.id))
    if existing:
        return existing
    if product:
        existing = db.scalar(select(PublishedPost).where(PublishedPost.product_id == product.id))
        if existing:
            return existing
    caption = build_publish_caption(draft.text, product)
    buttons = build_cta_buttons(product)
    publisher = TelegramPublisher()
    runtime = load_runtime_config(db)
    channel_id = None
    if product and product.project and product.project.telegram_channel_id:
        channel_id = product.project.telegram_channel_id
    elif draft.project and draft.project.telegram_channel_id:
        channel_id = draft.project.telegram_channel_id
    else:
        channel_id = runtime.telegram_channel_id
    log = PublishLog(
        project_id=draft.project_id,
        draft_id=draft.id,
        product_id=draft.product_id,
        channel=channel_id or "",
        status="pending",
        payload_json=json.dumps({"buttons": buttons, "caption": caption}, ensure_ascii=False),
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    result = await publisher.send_post(caption=caption, image_path=draft.image_path, buttons=buttons, channel_id=channel_id)
    if result.ok:
        draft.status = "published"
        draft.published_at = datetime.utcnow()
        draft.telegram_message_id = result.message_id
        draft.telegram_chat_id = result.chat_id
        if product:
            product.is_published = True
        published = PublishedPost(
            project_id=draft.project_id,
            draft_id=draft.id,
            product_id=draft.product_id,
            telegram_message_id=result.message_id,
            telegram_chat_id=result.chat_id,
            caption=caption,
            published_at=datetime.utcnow(),
            is_verified=False,
        )
        log.status = "published"
        log.telegram_message_id = result.message_id
        db.add(published)
        db.commit()
        db.refresh(published)
        return published

    draft.status = "publish_failed"
    log.status = "failed"
    log.error = result.error
    db.commit()
    raise RuntimeError(result.error or "Telegram publish failed")
