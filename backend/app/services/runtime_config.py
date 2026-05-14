from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import AppSetting


RUNTIME_KEYS = [
    "telegram_bot_token",
    "telegram_bot_username",
    "telegram_admin_id",
    "yookassa_shop_id",
    "yookassa_secret_key",
    "yookassa_return_url",
    "cryptobot_api_token",
    "cryptobot_asset",
    "ozon_feed_url",
    "wildberries_feed_url",
    "yandex_market_feed_url",
    "marketplace_demo_mode",
]

SECRET_KEYS = {"telegram_bot_token", "yookassa_secret_key", "cryptobot_api_token"}


@dataclass
class RuntimeConfig:
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_admin_id: int = 0
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = "http://localhost:5173"
    cryptobot_api_token: str = ""
    cryptobot_asset: str = "USDT"
    ozon_feed_url: str = ""
    wildberries_feed_url: str = ""
    yandex_market_feed_url: str = ""
    marketplace_demo_mode: str = "false"


def _setting_value(db: Session, key: str, fallback: str = "") -> str:
    item = db.get(AppSetting, key)
    if item and item.value not in (None, ""):
        return item.value
    return fallback


def load_runtime_config(db: Session | None = None) -> RuntimeConfig:
    settings = get_settings()
    close_db = False
    if db is None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        close_db = True
    try:
        admin_id_raw = _setting_value(db, "telegram_admin_id", str(settings.telegram_admin_id or ""))
        try:
            admin_id = int(admin_id_raw or 0)
        except ValueError:
            admin_id = 0
        return RuntimeConfig(
            telegram_bot_token=_setting_value(db, "telegram_bot_token", settings.telegram_bot_token),
            telegram_bot_username=_setting_value(db, "telegram_bot_username", settings.telegram_bot_username),
            telegram_admin_id=admin_id,
            yookassa_shop_id=_setting_value(db, "yookassa_shop_id", settings.yookassa_shop_id),
            yookassa_secret_key=_setting_value(db, "yookassa_secret_key", settings.yookassa_secret_key),
            yookassa_return_url=_setting_value(db, "yookassa_return_url", settings.yookassa_return_url),
            cryptobot_api_token=_setting_value(db, "cryptobot_api_token", settings.cryptobot_api_token),
            cryptobot_asset=_setting_value(db, "cryptobot_asset", settings.cryptobot_asset),
            ozon_feed_url=_setting_value(db, "ozon_feed_url", settings.ozon_feed_url),
            wildberries_feed_url=_setting_value(db, "wildberries_feed_url", settings.wildberries_feed_url),
            yandex_market_feed_url=_setting_value(db, "yandex_market_feed_url", settings.yandex_market_feed_url),
            marketplace_demo_mode=_setting_value(db, "marketplace_demo_mode", str(settings.marketplace_demo_mode).lower()),
        )
    finally:
        if close_db:
            db.close()


def mask_secret(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}••••{value[-4:]}"


def public_runtime_settings(db: Session) -> list[dict[str, str]]:
    config = load_runtime_config(db)
    values = config.__dict__
    result: list[dict[str, str]] = []
    for key in RUNTIME_KEYS:
        value = str(values.get(key) or "")
        result.append({"key": key, "value": mask_secret(value) if key in SECRET_KEYS else value})
    return result
