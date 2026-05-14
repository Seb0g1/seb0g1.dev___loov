from __future__ import annotations

import json
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


def parse_focus_categories(raw: str | None) -> list[str]:
    if not raw:
        return []
    value = raw.strip()
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip().lower() for item in parsed if str(item).strip()]
    except Exception:
        pass
    normalized = value.replace(";", ",").replace("\n", ",").replace("|", ",")
    return [item.strip().lower() for item in normalized.split(",") if item.strip()]


def _haystack(product: MarketplaceProduct) -> str:
    parts = [
        product.title,
        product.brand or "",
        product.category or "",
        product.description or "",
        json.dumps(product.characteristics, ensure_ascii=False),
    ]
    return " ".join(parts).lower()


def product_matches_focus(product: MarketplaceProduct, focus_categories: list[str]) -> bool:
    if not focus_categories:
        return True
    haystack = _haystack(product)
    normalized_category = (product.category or "").strip().lower()
    for category in focus_categories:
        token = category.strip().lower()
        if not token:
            continue
        if token == normalized_category:
            return True
        if token in haystack:
            return True
    return False
