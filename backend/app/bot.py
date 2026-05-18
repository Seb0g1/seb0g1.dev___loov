from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrations import ensure_project_schema
from app.db.session import SessionLocal, engine
from app.models import entities  # noqa: F401
from app.models.entities import AdRequest, DraftPost, Product, Project
from app.services.advertising import get_active_ad_packages, notify_admin_with_media
from app.services.drafts import create_draft_from_product
from app.services.importer import import_products
from app.services.review_actions import process_draft_decision
from app.services.runtime_config import load_runtime_config
from app.services.seed import seed_defaults

logger = logging.getLogger(__name__)


def _bootstrap_database() -> None:
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            Base.metadata.create_all(bind=engine)
            ensure_project_schema(engine)
            db = SessionLocal()
            try:
                seed_defaults(db)
            finally:
                db.close()
            ensure_project_schema(engine)
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Bot database bootstrap attempt %s failed: %s", attempt, exc)
            time.sleep(2)
    raise RuntimeError(f"Bot database bootstrap failed: {last_error}")


def _admin_only(settings, user_id: int | None) -> bool:
    return bool(settings.telegram_admin_id and user_id == settings.telegram_admin_id)


async def cmd_start(message: Message) -> None:
    await message.answer(
        "Админ-пульт готов.\n"
        "Команды: /status, /queue, /import, /drafts, /make_draft <product_id>, /ad"
    )


async def cmd_ad(message: Message) -> None:
    packages = []
    db = SessionLocal()
    try:
        packages = get_active_ad_packages(db)
    finally:
        db.close()

    lines = [
        "Пришлите текст рекламы и, если нужно, фото. "
        "После этого нажмите кнопку отправки на проверку."
    ]
    if packages:
        lines.append("Доступные пакеты:")
        for item in packages:
            lines.append(f"- {item.name}: {item.amount:,.0f} ₽".replace(",", " "))
    await message.answer("\n".join(lines))


async def cmd_status(message: Message) -> None:
    db = SessionLocal()
    try:
        projects = db.scalar(select(func.count()).select_from(Project)) or 0
        products = db.scalar(select(func.count()).select_from(Product)) or 0
        drafts = db.scalar(select(func.count()).select_from(DraftPost)) or 0
        pending = db.scalar(select(func.count()).select_from(DraftPost).where(DraftPost.status == "review")) or 0
        ads = db.scalar(select(func.count()).select_from(AdRequest)) or 0
        await message.answer(
            f"Проекты: {projects}\n"
            f"Товары: {products}\n"
            f"Черновики: {drafts}\n"
            f"На согласовании: {pending}\n"
            f"Рекламные заявки: {ads}"
        )
    finally:
        db.close()


async def cmd_queue(message: Message) -> None:
    db = SessionLocal()
    try:
        drafts = db.scalars(
            select(DraftPost)
            .where(DraftPost.status == "review")
            .order_by(DraftPost.created_at.desc())
            .limit(10)
        ).all()
        if not drafts:
            await message.answer("Очередь на согласование пустая.")
            return
        lines = []
        for draft in drafts:
            project_name = draft.project.name if draft.project else "Проект"
            lines.append(f"{draft.id}. {project_name} - {draft.title}")
        await message.answer("\n".join(lines))
    finally:
        db.close()


async def cmd_import(message: Message) -> None:
    db = SessionLocal()
    try:
        projects = db.scalars(select(Project).where(Project.is_active.is_(True))).all()
        imported = 0
        skipped = 0
        for project in projects:
            result = import_products(db, project)
            imported += result["imported"]
            skipped += result["skipped"]
        await message.answer(f"Импорт завершен: {imported} импортировано, {skipped} пропущено")
    except Exception as exc:
        logger.exception("Import failed: %s", exc)
        await message.answer(f"Ошибка импорта: {exc}")
    finally:
        db.close()


async def cmd_drafts(message: Message) -> None:
    db = SessionLocal()
    try:
        drafts = db.scalars(
            select(DraftPost)
            .order_by(DraftPost.created_at.desc())
            .limit(10)
        ).all()
        if not drafts:
            await message.answer("Черновиков пока нет.")
            return
        text = "\n".join(f"{draft.id}. {draft.title} [{draft.status}]" for draft in drafts)
        await message.answer(text)
    finally:
        db.close()


async def cmd_make_draft(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /make_draft <product_id>")
        return
    product_id = int(parts[1])
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if not product:
            await message.answer("Товар не найден")
            return
        draft = await create_draft_from_product(db, product)
        await message.answer(f"Черновик создан: {draft.id}")
    except Exception as exc:
        logger.exception("Draft generation failed: %s", exc)
        await message.answer(f"Ошибка создания черновика: {exc}")
    finally:
        db.close()


async def handle_ad_message(message: Message) -> None:
    settings = load_runtime_config()
    if not message.from_user or _admin_only(settings, message.from_user.id):
        return
    if message.chat.type != "private":
        return
    text = message.text or message.caption
    if not text and not message.photo:
        return

    db = SessionLocal()
    try:
        media_type = "photo" if message.photo else "text"
        media_file_id = message.photo[-1].file_id if message.photo else None
        media_local_path = None
        if media_file_id and message.bot:
            dest_dir = Path(get_settings().ads_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            media_local_path = str(dest_dir / f"{message.from_user.id}_{message.message_id}.jpg")
            await message.bot.download(media_file_id, destination=media_local_path)
        request = AdRequest(
            user_id=message.from_user.id,
            chat_id=str(message.chat.id),
            username=message.from_user.username,
            full_name=" ".join(part for part in [message.from_user.first_name, message.from_user.last_name] if part),
            text=text or "",
            media_type=media_type,
            media_file_id=media_file_id,
            media_local_path=media_local_path,
            status="draft",
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        await message.answer(
            "Заявка сохранена. Нажмите кнопку ниже, чтобы отправить текст рекламы на проверку.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Скинуть текст рекламы на проверку",
                            callback_data=f"ad_submit:{request.id}",
                        )
                    ]
                ]
            ),
        )
    finally:
        db.close()


async def handle_ad_submit(call: CallbackQuery) -> None:
    settings = load_runtime_config()
    if not call.from_user or _admin_only(settings, call.from_user.id):
        await call.answer()
        return
    parts = (call.data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        await call.answer("Некорректная заявка", show_alert=True)
        return
    request_id = int(parts[1])
    db = SessionLocal()
    try:
        request = db.get(AdRequest, request_id)
        if not request or request.user_id != call.from_user.id:
            await call.answer("Заявка не найдена", show_alert=True)
            return
        request.status = "submitted"
        db.commit()
        db.refresh(request)
        if call.message:
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
        await call.answer("Отправлено на проверку")
        await notify_admin_with_media(call.bot, request)
    except Exception as exc:
        logger.exception("Ad submit failed: %s", exc)
        await call.answer(f"Ошибка: {exc}", show_alert=True)
    finally:
        db.close()


async def handle_review_action(call: CallbackQuery) -> None:
    settings = load_runtime_config()
    if not _admin_only(settings, call.from_user.id if call.from_user else None):
        await call.answer("Нет доступа", show_alert=True)
        return

    parts = (call.data or "").split(":")
    if len(parts) != 3:
        await call.answer("Некорректная команда", show_alert=True)
        return

    action = parts[1].lower().strip()
    draft_id = int(parts[2]) if parts[2].isdigit() else None
    if not draft_id:
        await call.answer("Черновик не найден", show_alert=True)
        return

    db = SessionLocal()
    try:
        result = await process_draft_decision(db, draft_id, action)
        if not result.get("ok"):
            await call.answer(result.get("error", "Ошибка"), show_alert=True)
            return

        messages = {
            "approve": "Пост одобрен и опубликован",
            "reject": "Пост отменен",
            "redo": "Пост переделан",
            "next": "Взят другой товар",
        }
        if result.get("draft_id"):
            messages[action] = f"{messages.get(action, 'Готово')}. Новый черновик #{result['draft_id']} отправлен на проверку."
        elif result.get("message"):
            messages[action] = f"{messages.get(action, 'Готово')}: {result['message']}"

        await call.answer(messages.get(action, "Готово"), show_alert=False)
        if call.message:
            try:
                await call.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
    except Exception as exc:
        logger.exception("Review action failed: %s", exc)
        await call.answer(f"Ошибка: {exc}", show_alert=True)
    finally:
        db.close()


async def run_bot() -> None:
    _bootstrap_database()
    runtime = load_runtime_config()
    if not runtime.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=runtime.telegram_bot_token)
    dp = Dispatcher()
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_ad, Command("ad"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_queue, Command("queue"))
    dp.message.register(cmd_import, Command("import"))
    dp.message.register(cmd_drafts, Command("drafts"))
    dp.message.register(cmd_make_draft, Command("make_draft"))
    dp.message.register(handle_ad_message, F.chat.type == "private")
    dp.callback_query.register(handle_ad_submit, F.data.startswith("ad_submit:"))
    dp.callback_query.register(handle_review_action, F.data.startswith("review:"))

    logger.info("Telegram bot polling started")
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(run_bot())
