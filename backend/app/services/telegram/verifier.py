from __future__ import annotations

import logging

from telethon import TelegramClient

from app.services.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)


async def verify_message_exists(channel: str, message_id: int) -> bool:
    settings = load_runtime_config()
    if not settings.telethon_api_id or not settings.telethon_api_hash:
        return False
    try:
        async with TelegramClient(
            settings.telethon_session_name,
            settings.telethon_api_id,
            settings.telethon_api_hash,
        ) as client:
            message = await client.get_messages(channel, ids=message_id)
            return message is not None
    except Exception as exc:
        logger.exception("Telegram verification failed: %s", exc)
        return False
