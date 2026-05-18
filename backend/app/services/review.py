from __future__ import annotations

import logging
from html import escape

from sqlalchemy.orm import Session

from app.models.entities import DraftPost
from app.services.marketplace_links import build_marketplace_footer, format_price_from
from app.services.runtime_config import load_runtime_config
from app.services.telegram import TelegramPublisher

logger = logging.getLogger(__name__)


def build_review_markup(draft_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Одобрить", "callback_data": f"review:approve:{draft_id}"},
                {"text": "Отменить", "callback_data": f"review:reject:{draft_id}"},
            ],
            [
                {"text": "Переделать", "callback_data": f"review:redo:{draft_id}"},
                {"text": "Другой товар", "callback_data": f"review:next:{draft_id}"},
            ],
        ]
    }


def build_review_caption(draft: DraftPost) -> str:
    project_name = escape(draft.project.name if draft.project else "Проект")
    product = draft.product
    product_line = ""
    if product:
        product_line = f"\n\n<b>{escape(product.title)}</b>\n{escape(product.category)} · {format_price_from(product.price)}"
    body = escape(draft.text.strip())
    if len(body) > 650:
        body = f"{body[:650].rstrip()}..."
    footer = f"\n\n{build_marketplace_footer(product)}" if product else ""
    return f"Новый черновик для согласования\n<b>{project_name}</b>{product_line}\n\n{body}{footer}"


async def send_draft_for_review(db: Session, draft: DraftPost) -> bool:
    settings = load_runtime_config(db)
    if not settings.telegram_bot_token or not settings.telegram_admin_id:
        return False
    publisher = TelegramPublisher()
    result = await publisher.send_post(
        caption=build_review_caption(draft),
        image_path=draft.image_path,
        channel_id=str(settings.telegram_admin_id),
        reply_markup=build_review_markup(draft.id),
    )
    if not result.ok:
        logger.warning("Failed to send review draft %s: %s", draft.id, result.error)
        return False
    return True
