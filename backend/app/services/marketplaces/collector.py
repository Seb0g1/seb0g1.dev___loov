from __future__ import annotations

import json

from app.services.marketplaces.common import parse_focus_categories, product_matches_focus
from app.core.config import get_settings
from app.services.marketplaces.demo import get_demo_products
from app.services.marketplaces.ozon import fetch_products as fetch_ozon
from app.services.marketplaces.wildberries import fetch_products as fetch_wb
from app.services.marketplaces.yandex_market import fetch_products as fetch_ym


def _parse_feed_config(project) -> dict[str, str]:
    raw = getattr(project, "feed_config_json", None)
    if not raw:
        return {}
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except Exception:
            return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    for key in ("ozon", "wildberries", "yandex_market"):
        value = data.get(key)
        if value:
            result[key] = str(value).strip()
    return result


def collect_marketplace_products(project, limit_per_source: int = 20):
    settings = get_settings()
    focus_categories = parse_focus_categories(getattr(project, "category_focus_json", None))
    feed_urls = _parse_feed_config(project)
    products = []
    try:
        products.extend(fetch_ozon(limit_per_source, feed_urls.get("ozon") or getattr(settings, "ozon_feed_url", None)))
    except Exception:
        pass
    try:
        products.extend(fetch_wb(limit_per_source, feed_urls.get("wildberries") or getattr(settings, "wildberries_feed_url", None)))
    except Exception:
        pass
    try:
        products.extend(fetch_ym(limit_per_source, feed_urls.get("yandex_market") or getattr(settings, "yandex_market_feed_url", None)))
    except Exception:
        pass
    if focus_categories:
        products = [product for product in products if product_matches_focus(product, focus_categories)]
    if not products and getattr(settings, "marketplace_demo_mode", False):
        products.extend(
            product
            for product in get_demo_products(project.slug)
            if not focus_categories or product_matches_focus(product, focus_categories)
        )
    return products
