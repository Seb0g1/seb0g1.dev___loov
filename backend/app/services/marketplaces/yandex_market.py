from __future__ import annotations

from urllib.parse import urlparse

from app.services.live_product import fetch_live_product_data_sync
from app.services.marketplace_links import build_marketplace_links
from app.services.marketplaces.base import MarketplaceProduct
from app.services.marketplaces.common import fetch_json_feed


def _is_yandex_product_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return "market.yandex" in host and ("/product--" in path or "/product/" in path)


def _with_live_price(product: MarketplaceProduct) -> MarketplaceProduct | None:
    if not _is_yandex_product_url(product.url):
        return None
    live = fetch_live_product_data_sync(product.url)
    if not live.price:
        return None
    product.price = live.price
    if live.market_price and live.price and live.market_price > live.price:
        product.market_price = live.market_price
        product.discount_percent = round((live.market_price - live.price) / live.market_price * 100, 1)
    if live.rating:
        product.rating = live.rating
    if live.reviews_count:
        product.reviews_count = live.reviews_count
    if product.price <= 0:
        return None
    characteristics = dict(product.characteristics or {})
    characteristics["marketplace_links"] = build_marketplace_links(
        {
            "source": product.source,
            "title": product.title,
            "brand": product.brand,
            "url": product.url,
            "characteristics": characteristics,
        }
    )
    characteristics["price_source"] = "live_product_page"
    product.characteristics = characteristics
    return product


def fetch_products(limit: int = 20, feed_url: str | None = None, category_hint: str | None = None) -> list[MarketplaceProduct]:
    products = fetch_json_feed("yandex_market", feed_url, limit * 2, category_hint)
    verified: list[MarketplaceProduct] = []
    for product in products:
        verified_product = _with_live_price(product)
        if verified_product:
            verified.append(verified_product)
        if len(verified) >= limit:
            break
    return verified[:limit]
