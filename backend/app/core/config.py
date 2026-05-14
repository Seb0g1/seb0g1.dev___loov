from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Техно Халява Admin"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "sqlite:///./tehno_halava.db"
    sqlite_path: str = "tehno_halava.db"

    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
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
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

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
    storage_dir: Path = Field(default=BASE_DIR / "storage")
    generated_dir: Path = Field(default=BASE_DIR / "storage" / "generated")
    ads_dir: Path = Field(default=BASE_DIR / "storage" / "ads")

    auto_posting_enabled: bool = False
    import_interval_minutes: int = 30
    publish_interval_minutes: int = 5

    telethon_api_id: int = 0
    telethon_api_hash: str = ""
    telethon_session_name: str = "tehno_halava_verifier"

    def cors_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.generated_dir.mkdir(parents=True, exist_ok=True)
    settings.ads_dir.mkdir(parents=True, exist_ok=True)
    return settings
