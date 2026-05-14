from __future__ import annotations

from dataclasses import asdict
from typing import Any

import httpx

from app.services.marketplaces.base import MarketplaceProduct


def _to_product(source: str, record: dict[str, Any]) -> MarketplaceProduct:
    return MarketplaceProduct(
        source=source,
        source_id=str(record.get("source_id") or record.get("id") or record.get("sku") or record.get("product_id") or record.get("offer_id") or ""),
        title=str(record.get("title") or record.get("name") or record.get("product_name") or "Unknown product"),
        brand=record.get("brand"),
        category=str(record.get("category") or record.get("category_name") or "general"),
        price=float(record.get("price") or record.get("current_price") or 0),
        market_price=float(record.get("market_price") or record.get("old_price") or record.get("price_before_discount") or 0) or None,
        discount_percent=float(record.get("discount_percent") or record.get("discount") or 0) or None,
        rating=float(record.get("rating") or record.get("score") or 0) or None,
        reviews_count=int(record.get("reviews_count") or record.get("reviews") or 0) or None,
        stock_count=int(record.get("stock_count") or record.get("stock") or 0) or None,
        url=record.get("url") or record.get("link"),
        description=record.get("description") or record.get("desc"),
        characteristics=record.get("characteristics") or record.get("attributes") or {},
        images=list(record.get("images") or record.get("photos") or []),
    )


def fetch_json_feed(source: str, feed_url: str | None, limit: int = 20) -> list[MarketplaceProduct]:
    if not feed_url:
        return []
    response = httpx.get(feed_url, timeout=30, follow_redirects=True)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):
        records = payload.get("items") or payload.get("results") or payload.get("data") or []
    else:
        records = payload

    products: list[MarketplaceProduct] = []
    for record in records[:limit]:
        if isinstance(record, dict):
            product = _to_product(source, record)
            if product.source_id and product.title:
                products.append(product)
    return products
