from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketplaceProduct:
    source: str
    source_id: str
    title: str
    brand: str | None
    category: str
    price: float
    market_price: float | None
    discount_percent: float | None
    rating: float | None
    reviews_count: int | None
    stock_count: int | None
    url: str | None
    description: str | None
    characteristics: dict
    images: list[str]

