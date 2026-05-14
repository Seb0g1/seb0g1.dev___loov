from __future__ import annotations

from dataclasses import dataclass


PRIORITY_CATEGORIES = {
    "laptops": 1.25,
    "monitors": 1.2,
    "keyboards": 1.18,
    "mice": 1.18,
    "headsets": 1.12,
    "accessories": 1.08,
    "components": 1.2,
    "general": 1.0,
}


@dataclass
class ScoredProduct:
    score: float
    reason: str


def _safe(value: float | int | None, default: float = 0.0) -> float:
    return float(value if value is not None else default)


def score_product(product: dict) -> ScoredProduct:
    price = max(_safe(product.get("price"), 0.0), 0.01)
    market_price = _safe(product.get("market_price"), 0.0)
    discount = _safe(product.get("discount_percent"), 0.0)
    rating = min(max(_safe(product.get("rating"), 0.0), 0.0), 5.0)
    reviews = max(_safe(product.get("reviews_count"), 0.0), 0.0)
    stock = _safe(product.get("stock_count"), 0.0)
    category = str(product.get("category") or "general").lower()

    market_bonus = 0.0
    if market_price > price > 0:
        market_bonus = min((market_price - price) / market_price * 100, 40)
    elif discount > 0:
        market_bonus = min(discount, 40)

    rating_bonus = rating / 5 * 20
    reviews_bonus = min(reviews ** 0.5 * 3, 15)
    stock_bonus = 6 if stock > 0 else -8
    category_bonus = PRIORITY_CATEGORIES.get(category, 1.0) * 10
    category_bonus -= 10

    score = market_bonus * 0.9 + rating_bonus + reviews_bonus + stock_bonus + category_bonus
    if price > 150000:
        score -= 5
    if rating and rating < 4:
        score -= 4
    if reviews < 10:
        score -= 2

    reason = f"market={market_bonus:.1f}, rating={rating_bonus:.1f}, reviews={reviews_bonus:.1f}, stock={stock_bonus:.1f}, category={category_bonus:.1f}"
    return ScoredProduct(score=round(score, 2), reason=reason)

