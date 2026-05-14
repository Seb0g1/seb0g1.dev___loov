from __future__ import annotations

from app.core.config import get_settings
from app.services.marketplaces.demo import get_demo_products
from app.services.marketplaces.ozon import fetch_products as fetch_ozon
from app.services.marketplaces.wildberries import fetch_products as fetch_wb
from app.services.marketplaces.yandex_market import fetch_products as fetch_ym


def collect_marketplace_products(project, limit_per_source: int = 20):
    settings = get_settings()
    products = []
    try:
        products.extend(fetch_ozon(limit_per_source))
    except Exception:
        pass
    try:
        products.extend(fetch_wb(limit_per_source))
    except Exception:
        pass
    try:
        products.extend(fetch_ym(limit_per_source))
    except Exception:
        pass
    if not products and getattr(settings, "marketplace_demo_mode", False):
        products.extend(get_demo_products(project.slug))
    return products
