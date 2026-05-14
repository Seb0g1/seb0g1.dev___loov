from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AdPackage, AdRequest, Project
from app.services.payments import create_payment_link
from app.services.runtime_config import load_runtime_config
from app.services.telegram import TelegramPublisher

logger = logging.getLogger(__name__)


def build_ad_packages_text(package: AdPackage | None = None) -> str:
    if package:
        return (
            f"Реклама во всех каналах 24 часа в истории и ленте.\n"
            f"Пакет: {package.name}\n"
            f"Цена: {package.amount:,.0f} ₽".replace(",", " ")
        )
    return "Реклама во всех каналах 24 часа в истории и ленте."


def ad_request_to_caption(request: AdRequest) -> str:
    lines = [
        "Заявка на рекламу",
        f"От: {request.full_name or request.username or request.user_id}",
        f"Статус: {request.status}",
    ]
    if request.package_name:
        lines.append(f"Пакет: {escape(request.package_name)}")
    if request.amount is not None:
        lines.append(f"Сумма: {request.amount:,.0f} ₽".replace(",", " "))
    if request.admin_note:
        lines.append(f"Комментарий: {escape(request.admin_note)}")
    lines.append("")
    lines.append(escape(request.text))
    return "\n".join(lines)


def build_payment_buttons(payment_links: dict[str, str]) -> list[dict]:
    buttons: list[dict] = []
    for label, url in payment_links.items():
        if url:
            buttons.append({"text": label, "url": url})
    return buttons


def get_active_ad_packages(db: Session) -> list[AdPackage]:
    return db.scalars(select(AdPackage).where(AdPackage.is_active.is_(True)).order_by(AdPackage.sort_order.asc(), AdPackage.id.asc())).all()


async def notify_admin_about_request(db: Session, request: AdRequest) -> None:
    settings = load_runtime_config(db)
    if not settings.telegram_bot_token or not settings.telegram_admin_id:
        return
    publisher = TelegramPublisher()
    result = await publisher.send_message(
        chat_id=str(settings.telegram_admin_id),
        text=ad_request_to_caption(request),
    )
    if not result.ok:
        logger.warning("Failed to notify admin about ad request %s", request.id)


async def notify_admin_with_media(bot: Bot, request: AdRequest) -> None:
    settings = load_runtime_config()
    if not settings.telegram_admin_id:
        return
    try:
        if request.media_local_path and Path(request.media_local_path).exists():
            await bot.send_photo(
                chat_id=settings.telegram_admin_id,
                photo=FSInputFile(request.media_local_path),
                caption=f"Заявка на рекламу #{request.id}",
            )
            await bot.send_message(chat_id=settings.telegram_admin_id, text=ad_request_to_caption(request))
        else:
            await bot.send_message(chat_id=settings.telegram_admin_id, text=ad_request_to_caption(request))
    except Exception as exc:
        logger.exception("Failed to send ad request to admin: %s", exc)


async def send_payment_offer(db: Session, request: AdRequest, provider: str, package: AdPackage) -> dict:
    provider = provider.lower().strip()
    payment_links: dict[str, str] = {}
    payment_id = None
    amount = package.amount
    description = f"{package.name} | заявка #{request.id}"
    if provider in {"both", "all"}:
        for provider_name, label in [("yookassa", "Оплатить YooKassa"), ("cryptobot", "Оплатить CryptoBot")]:
            result = await create_payment_link(provider_name, amount, description, request.id)
            if result.ok and result.payment_url:
                payment_links[label] = result.payment_url
                payment_id = payment_id or result.payment_id
        if not payment_links:
            raise RuntimeError("No payment links could be created")
    else:
        result = await create_payment_link(provider, amount, description, request.id)
        if not result.ok or not result.payment_url:
            raise RuntimeError(result.error or "Payment link could not be created")
        label = "Оплатить YooKassa" if provider == "yookassa" else "Оплатить CryptoBot"
        payment_links[label] = result.payment_url
        payment_id = result.payment_id

    request.package_id = package.id
    request.package_name = package.name
    request.amount = amount
    request.payment_provider = provider
    request.payment_url = next(iter(payment_links.values()), None)
    request.payment_links_json = json.dumps(payment_links, ensure_ascii=False)
    request.external_payment_id = payment_id
    request.status = "awaiting_payment"
    db.commit()
    db.refresh(request)
    return payment_links


async def send_payment_message_to_user(request: AdRequest, package: AdPackage, payment_links: dict[str, str]) -> bool:
    settings = load_runtime_config()
    if not settings.telegram_bot_token:
        return False
    publisher = TelegramPublisher()
    result = await publisher.send_message(
        chat_id=request.chat_id,
        text=(
            f"Пакет: {package.name}\n"
            f"Сумма: {package.amount:,.0f} ₽\n"
            f"Срок: {package.duration_hours} ч.\n\n"
            f"Реклама во всех каналах 24 часа в истории и ленте."
        ).replace(",", " "),
        buttons=build_payment_buttons(payment_links),
    )
    return result.ok


async def send_paid_notice_to_user(request: AdRequest) -> bool:
    publisher = TelegramPublisher()
    result = await publisher.send_message(
        chat_id=request.chat_id,
        text="Оплата получена. Пост в работе, скоро отправим ссылку на публикацию.",
    )
    return result.ok


async def send_publication_link_to_user(request: AdRequest) -> bool:
    if not request.published_link:
        return False
    publisher = TelegramPublisher()
    result = await publisher.send_message(
        chat_id=request.chat_id,
        text=f"Пост опубликован. Ссылка: {request.published_link}",
    )
    return result.ok


async def send_review_to_admin(request: AdRequest) -> bool:
    publisher = TelegramPublisher()
    caption = ad_request_to_caption(request)
    buttons = [{"text": "Открыть в панели", "url": "http://localhost:5173"}]
    runtime = load_runtime_config()
    result = await publisher.send_message(
        chat_id=str(runtime.telegram_admin_id),
        text=caption,
        buttons=buttons,
    )
    return result.ok


async def publish_ad_to_channels(db: Session, request: AdRequest) -> dict[str, str]:
    projects = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.sort_order.asc(), Project.id.asc())).all()
    publisher = TelegramPublisher()
    links: dict[str, str] = {}
    message_ids: dict[str, int] = {}
    caption = request.text
    for project in projects:
        channel_id = project.telegram_channel_id or ""
        if not channel_id:
            continue
        if request.media_local_path and Path(request.media_local_path).exists():
            result = await publisher.send_post(caption=caption, image_path=request.media_local_path, channel_id=channel_id)
        else:
            result = await publisher.send_post(caption=caption, channel_id=channel_id)
        if not result.ok:
            continue
        message_ids[project.slug] = result.message_id or 0
        if project.telegram_channel_url and result.message_id:
            base = project.telegram_channel_url.rstrip("/")
            links[project.slug] = f"{base}/{result.message_id}"
    request.published_message_ids_json = json.dumps(message_ids, ensure_ascii=False)
    request.published_link = next(iter(links.values()), request.published_link)
    request.status = "published"
    request.published_at = datetime.utcnow()
    request.delete_at = datetime.utcnow() + timedelta(hours=request.package.delete_after_hours if request.package else 24)
    db.commit()
    db.refresh(request)
    return links


async def delete_expired_ad_posts(db: Session) -> int:
    now = datetime.utcnow()
    requests = db.scalars(
        select(AdRequest).where(
            AdRequest.status == "published",
            AdRequest.delete_at.is_not(None),
            AdRequest.delete_at <= now,
        )
    ).all()
    if not requests:
        return 0
    publisher = TelegramPublisher()
    deleted = 0
    for request in requests:
        message_ids = json.loads(request.published_message_ids_json or "{}")
        for project_slug, message_id in message_ids.items():
            if not message_id:
                continue
            project = db.scalar(select(Project).where(Project.slug == project_slug))
            if not project or not project.telegram_channel_id:
                continue
            await publisher.delete_message(project.telegram_channel_id, int(message_id))
        request.status = "deleted"
        request.deleted_at = now
        deleted += 1
    db.commit()
    return deleted
