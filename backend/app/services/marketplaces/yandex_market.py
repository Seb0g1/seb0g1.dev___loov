from __future__ import annotations

from app.core.config import get_settings
from app.services.marketplaces.base import MarketplaceProduct
from app.services.marketplaces.common import fetch_json_feed


def fetch_products(limit: int = 20) -> list[MarketplaceProduct]:
    settings = get_settings()
    return fetch_json_feed("yandex_market", getattr(settings, "yandex_market_feed_url", None), limit)
