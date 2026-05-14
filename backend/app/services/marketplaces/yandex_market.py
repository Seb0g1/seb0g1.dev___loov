from __future__ import annotations

from app.services.marketplaces.base import MarketplaceProduct
from app.services.marketplaces.common import fetch_json_feed


def fetch_products(limit: int = 20, feed_url: str | None = None) -> list[MarketplaceProduct]:
    return fetch_json_feed("yandex_market", feed_url, limit)
