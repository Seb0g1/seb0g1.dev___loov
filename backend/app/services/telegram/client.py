from __future__ import annotations

import logging
import json
from dataclasses import dataclass

import httpx

from app.services.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)


@dataclass
class TelegramPublishResult:
    ok: bool
    message_id: int | None
    chat_id: str | None
    raw: dict
    error: str | None = None


class TelegramPublisher:
    def __init__(self) -> None:
        self.runtime = load_runtime_config()

    @property
    def enabled(self) -> bool:
        return bool(self.runtime.telegram_bot_token and self.runtime.telegram_channel_id)

    async def send_post(
        self,
        caption: str,
        image_path: str | None = None,
        buttons: list[dict] | None = None,
        channel_id: str | None = None,
        reply_markup: dict | None = None,
    ) -> TelegramPublishResult:
        target_channel = channel_id or self.runtime.telegram_channel_id
        if not self.runtime.telegram_bot_token or not target_channel:
            return TelegramPublishResult(ok=False, message_id=None, chat_id=None, raw={}, error="Telegram is not configured")

        payload = {
            "chat_id": target_channel,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        elif buttons:
            payload["reply_markup"] = json.dumps({"inline_keyboard": [buttons]}, ensure_ascii=False)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                if image_path:
                    with open(image_path, "rb") as file:
                        files = {"photo": file}
                        response = await client.post(
                            f"https://api.telegram.org/bot{self.runtime.telegram_bot_token}/sendPhoto",
                            data={**payload, "caption": caption},
                            files=files,
                        )
                else:
                    response = await client.post(
                        f"https://api.telegram.org/bot{self.runtime.telegram_bot_token}/sendMessage",
                        data={**payload, "text": caption},
                    )
                response.raise_for_status()
                data = response.json()
                result = data.get("result", {})
                return TelegramPublishResult(
                    ok=True,
                    message_id=result.get("message_id"),
                    chat_id=str(result.get("chat", {}).get("id")) if result else self.runtime.telegram_channel_id,
                    raw=data,
                )
        except Exception as exc:
            logger.exception("Telegram publish failed: %s", exc)
            return TelegramPublishResult(ok=False, message_id=None, chat_id=self.runtime.telegram_channel_id, raw={}, error=str(exc))

    async def send_message(
        self,
        chat_id: str,
        text: str,
        buttons: list[dict] | None = None,
        reply_markup: dict | None = None,
    ) -> TelegramPublishResult:
        return await self.send_post(caption=text, buttons=buttons, channel_id=chat_id, reply_markup=reply_markup)

    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        if not self.runtime.telegram_bot_token:
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.runtime.telegram_bot_token}/deleteMessage",
                    data={"chat_id": chat_id, "message_id": message_id},
                )
                response.raise_for_status()
                data = response.json()
                return bool(data.get("ok"))
        except Exception as exc:
            logger.exception("Telegram delete failed: %s", exc)
            return False
