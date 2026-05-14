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
    "text_engine",
    "openrouter_api_key",
    "openrouter_base_url",
    "openrouter_text_model",
    "openrouter_text_timeout_seconds",
    "openrouter_text_max_tokens",
    "openrouter_site_url",
    "openrouter_site_name",
    "image_engine",
    "codex_sale_api_key",
    "codex_sale_base_url",
    "codex_sale_image_model",
    "codex_sale_image_size",
    "codex_sale_timeout_seconds",
    "image_generation_mode",
    "ozon_feed_url",
    "wildberries_feed_url",
    "yandex_market_feed_url",
    "marketplace_demo_mode",
    "auto_posting_enabled",
    "import_interval_minutes",
    "publish_interval_minutes",
    "telethon_api_id",
    "telethon_api_hash",
    "telethon_session_name",
]

SECRET_KEYS = {
    "telegram_bot_token",
    "yookassa_secret_key",
    "cryptobot_api_token",
    "openrouter_api_key",
    "codex_sale_api_key",
    "telethon_api_hash",
}


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
    text_engine: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_text_model: str = "openrouter/cypher-alpha:free"
    openrouter_text_timeout_seconds: int = 180
    openrouter_text_max_tokens: int = 900
    openrouter_site_url: str = ""
    openrouter_site_name: str = ""
    image_engine: str = "codex_sale"
    codex_sale_api_key: str = ""
    codex_sale_base_url: str = "https://codex.sale/v1"
    codex_sale_image_model: str = "gpt-image-2"
    codex_sale_image_size: str = "1024x1024"
    codex_sale_timeout_seconds: int = 300
    image_generation_mode: str = "image_to_image"
    ozon_feed_url: str = ""
    wildberries_feed_url: str = ""
    yandex_market_feed_url: str = ""
    marketplace_demo_mode: bool = False
    auto_posting_enabled: bool = False
    import_interval_minutes: int = 30
    publish_interval_minutes: int = 5
    telethon_api_id: int = 0
    telethon_api_hash: str = ""
    telethon_session_name: str = "tehno_halava_verifier"


def _setting_value(db: Session, key: str, fallback: str = "") -> str:
    item = db.get(AppSetting, key)
    if item and item.value not in (None, ""):
        return item.value
    return fallback


def _as_int(value: str | int | None, fallback: int) -> int:
    try:
        return int(value) if value not in (None, "") else fallback
    except (TypeError, ValueError):
        return fallback


def _as_bool(value: str | bool | None, fallback: bool = False) -> bool:
    if value in (None, ""):
        return fallback
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config(db: Session | None = None) -> RuntimeConfig:
    settings = get_settings()
    close_db = False
    if db is None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        close_db = True
    try:
        admin_id_raw = _setting_value(db, "telegram_admin_id", str(settings.telegram_admin_id or ""))
        return RuntimeConfig(
            telegram_bot_token=_setting_value(db, "telegram_bot_token", settings.telegram_bot_token),
            telegram_bot_username=_setting_value(db, "telegram_bot_username", settings.telegram_bot_username),
            telegram_admin_id=_as_int(admin_id_raw, settings.telegram_admin_id or 0),
            yookassa_shop_id=_setting_value(db, "yookassa_shop_id", settings.yookassa_shop_id),
            yookassa_secret_key=_setting_value(db, "yookassa_secret_key", settings.yookassa_secret_key),
            yookassa_return_url=_setting_value(db, "yookassa_return_url", settings.yookassa_return_url),
            cryptobot_api_token=_setting_value(db, "cryptobot_api_token", settings.cryptobot_api_token),
            cryptobot_asset=_setting_value(db, "cryptobot_asset", settings.cryptobot_asset),
            text_engine=_setting_value(db, "text_engine", settings.text_engine),
            openrouter_api_key=_setting_value(db, "openrouter_api_key", settings.openrouter_api_key),
            openrouter_base_url=_setting_value(db, "openrouter_base_url", settings.openrouter_base_url),
            openrouter_text_model=_setting_value(db, "openrouter_text_model", settings.openrouter_text_model),
            openrouter_text_timeout_seconds=_as_int(
                _setting_value(db, "openrouter_text_timeout_seconds", str(settings.openrouter_text_timeout_seconds)),
                settings.openrouter_text_timeout_seconds,
            ),
            openrouter_text_max_tokens=_as_int(
                _setting_value(db, "openrouter_text_max_tokens", str(settings.openrouter_text_max_tokens)),
                settings.openrouter_text_max_tokens,
            ),
            openrouter_site_url=_setting_value(db, "openrouter_site_url", settings.openrouter_site_url),
            openrouter_site_name=_setting_value(db, "openrouter_site_name", settings.openrouter_site_name),
            image_engine=_setting_value(db, "image_engine", settings.image_engine),
            codex_sale_api_key=_setting_value(db, "codex_sale_api_key", settings.codex_sale_api_key),
            codex_sale_base_url=_setting_value(db, "codex_sale_base_url", settings.codex_sale_base_url),
            codex_sale_image_model=_setting_value(db, "codex_sale_image_model", settings.codex_sale_image_model),
            codex_sale_image_size=_setting_value(db, "codex_sale_image_size", settings.codex_sale_image_size),
            codex_sale_timeout_seconds=_as_int(
                _setting_value(db, "codex_sale_timeout_seconds", str(settings.codex_sale_timeout_seconds)),
                settings.codex_sale_timeout_seconds,
            ),
            image_generation_mode=_setting_value(db, "image_generation_mode", settings.image_generation_mode),
            ozon_feed_url=_setting_value(db, "ozon_feed_url", settings.ozon_feed_url),
            wildberries_feed_url=_setting_value(db, "wildberries_feed_url", settings.wildberries_feed_url),
            yandex_market_feed_url=_setting_value(db, "yandex_market_feed_url", settings.yandex_market_feed_url),
            marketplace_demo_mode=_as_bool(
                _setting_value(db, "marketplace_demo_mode", str(settings.marketplace_demo_mode).lower()),
                settings.marketplace_demo_mode,
            ),
            auto_posting_enabled=_as_bool(
                _setting_value(db, "auto_posting_enabled", str(settings.auto_posting_enabled).lower()),
                settings.auto_posting_enabled,
            ),
            import_interval_minutes=_as_int(
                _setting_value(db, "import_interval_minutes", str(settings.import_interval_minutes)),
                settings.import_interval_minutes,
            ),
            publish_interval_minutes=_as_int(
                _setting_value(db, "publish_interval_minutes", str(settings.publish_interval_minutes)),
                settings.publish_interval_minutes,
            ),
            telethon_api_id=_as_int(_setting_value(db, "telethon_api_id", str(settings.telethon_api_id)), settings.telethon_api_id),
            telethon_api_hash=_setting_value(db, "telethon_api_hash", settings.telethon_api_hash),
            telethon_session_name=_setting_value(db, "telethon_session_name", settings.telethon_session_name),
        )
    finally:
        if close_db:
            db.close()


def public_runtime_settings(db: Session) -> list[dict[str, str]]:
    config = load_runtime_config(db)
    values = config.__dict__
    result: list[dict[str, str]] = []
    for key in RUNTIME_KEYS:
        value = str(values.get(key) or "")
        result.append({"key": key, "value": "[saved]" if key in SECRET_KEYS and value else value})
    return result
