from __future__ import annotations

import json
from collections import defaultdict
from typing import Any
from urllib.parse import quote_plus

from app.services.marketplaces.common import parse_focus_categories, product_matches_focus
from app.services.marketplaces.demo import get_demo_products
from app.services.marketplaces.ozon import fetch_products as fetch_ozon
from app.services.marketplaces.wildberries import fetch_products as fetch_wb
from app.services.marketplaces.yandex_market import fetch_products as fetch_ym
from app.services.runtime_config import load_runtime_config


MARKETPLACE_ALIASES = {
    "ozon": "ozon",
    "wildberries": "wildberries",
    "wb": "wildberries",
    "yandex_market": "yandex_market",
    "yandex market": "yandex_market",
    "yandex": "yandex_market",
    "ym": "yandex_market",
}

FETCHERS = {
    "ozon": fetch_ozon,
    "wildberries": fetch_wb,
    "yandex_market": fetch_ym,
}


def _normalize_marketplace(value: Any) -> str:
    return MARKETPLACE_ALIASES.get(str(value or "").strip().lower(), "")


FEED_SEARCH_ALIASES = {
    "bedding": "постельное белье",
    "lamps": "лампа",
    "organizers": "органайзер",
    "tableware": "посуда",
    "protein": "протеин",
    "vitamins": "витамины",
    "creatine": "креатин",
    "omega-3": "омега 3",
    "sneakers": "кроссовки",
    "apparel": "одежда",
    "streetwear": "streetwear",
    "laptops": "ноутбук",
    "monitors": "монитор",
    "keyboards": "клавиатура",
    "mice": "мышь",
    "components": "комплектующие",
    "headphones": "наушники",
    "headset": "гарнитура",
    "accessories": "аксессуары",
    "pc-case": "корпус",
    "computer-case": "корпус",
    "power-supply": "блок питания",
    "motherboard": "материнская плата",
    "graphics-card": "видеокарта",
    "ssd": "ssd",
    "ram": "оперативная память",
}


def _marketplace_search_query(category: Any) -> str:
    raw = str(category or "").strip()
    if not raw:
        return ""
    tokens = [item.strip() for item in raw.replace(";", ",").replace("|", ",").replace("\n", ",").split(",") if item.strip()]
    mapped = [FEED_SEARCH_ALIASES.get(token.lower(), token) for token in tokens]
    seen: set[str] = set()
    query_parts: list[str] = []
    for token in mapped:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        query_parts.append(token)
    return " ".join(query_parts).strip()


def _build_marketplace_search_url(marketplace: Any, category: Any = "") -> str:
    normalized_marketplace = _normalize_marketplace(marketplace)
    query = _marketplace_search_query(category)
    if normalized_marketplace == "ozon":
        return f"https://www.ozon.ru/search/?text={quote_plus(query)}" if query else "https://www.ozon.ru/"
    if normalized_marketplace == "wildberries":
        return f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote_plus(query)}" if query else "https://www.wildberries.ru/"
    if normalized_marketplace == "yandex_market":
        return f"https://market.yandex.ru/search?text={quote_plus(query)}" if query else "https://market.yandex.ru/"
    return ""


def _split_categories(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    categories: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        normalized = text.replace(";", ",").replace("|", ",").replace("\n", ",")
        for item in normalized.split(","):
            token = item.strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            categories.append(token)
    return categories


def _feed_entries(marketplace: Any, url: Any, category: Any = "") -> list[dict[str, str]]:
    normalized_marketplace = _normalize_marketplace(marketplace)
    normalized_url = str(url or "").strip()
    if not normalized_marketplace:
        return []
    categories = _split_categories(category) or [""]
    search_query = _marketplace_search_query(category)
    search_url = normalized_url or (_build_marketplace_search_url(normalized_marketplace, category) if search_query else "")
    if not search_url:
        return []
    return [
        {
            "marketplace": normalized_marketplace,
            "url": search_url,
            "category": current_category,
        }
        for current_category in categories
    ]


def _parse_feed_config(project) -> list[dict[str, str]]:
    raw = getattr(project, "feed_config_json", None)
    if not raw:
        return []
    try:
        data = raw if isinstance(raw, (dict, list)) else json.loads(raw)
    except Exception:
        return []

    entries: list[dict[str, str]] = []
    if isinstance(data, dict):
        for marketplace, value in data.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        entries.extend(_feed_entries(marketplace, item.get("url"), item.get("category") or item.get("label")))
                    else:
                        entries.extend(_feed_entries(marketplace, item))
            elif isinstance(value, dict):
                entries.extend(_feed_entries(marketplace, value.get("url"), value.get("category") or value.get("label")))
            else:
                entries.extend(_feed_entries(marketplace, value))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            entries.extend(_feed_entries(
                item.get("marketplace") or item.get("source"),
                item.get("url") or item.get("feed_url"),
                item.get("category") or item.get("label"),
            ))
    return entries


def _global_feed_entries(settings) -> list[dict[str, str]]:
    rows = [
        *_feed_entries("ozon", getattr(settings, "ozon_feed_url", ""), ""),
        *_feed_entries("wildberries", getattr(settings, "wildberries_feed_url", ""), ""),
        *_feed_entries("yandex_market", getattr(settings, "yandex_market_feed_url", ""), ""),
    ]
    return [row for row in rows if row]


def project_feed_entries(project) -> list[dict[str, str]]:
    return _parse_feed_config(project)


def global_feed_entries(settings) -> list[dict[str, str]]:
    return _global_feed_entries(settings)


def _fetch_entries(entries: list[dict[str, str]], limit_per_source: int):
    products = []
    seen_urls_by_marketplace: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for entry in entries:
        marketplace = entry["marketplace"]
        feed_url = entry["url"]
        signature = (feed_url, entry.get("category") or "")
        if signature in seen_urls_by_marketplace[marketplace]:
            continue
        seen_urls_by_marketplace[marketplace].add(signature)
        fetcher = FETCHERS.get(marketplace)
        if not fetcher:
            continue
        try:
            products.extend(fetcher(limit_per_source, feed_url, entry.get("category") or None))
        except Exception:
            continue
    return products


def test_marketplace_feed(marketplace: str, feed_url: str, category: str | None = None, limit: int = 10):
    normalized_marketplace = _normalize_marketplace(marketplace)
    fetcher = FETCHERS.get(normalized_marketplace)
    if not fetcher:
        raise ValueError("Unknown marketplace")
    search_query = _marketplace_search_query(category)
    normalized_feed_url = str(feed_url or "").strip() or (_build_marketplace_search_url(normalized_marketplace, category) if search_query else "")
    if not normalized_feed_url:
        return []
    categories = _split_categories(category)
    category_variants: list[str | None] = categories or [None]
    products = []
    seen_keys: set[tuple[str, str | None, str]] = set()
    for category_variant in category_variants:
        for item in fetcher(limit, normalized_feed_url, category_variant):
            key = (item.source_id, item.url, item.title)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            products.append(item)
            if len(products) >= limit:
                return products[:limit]
    return products[:limit]


def collect_marketplace_products(project, limit_per_source: int = 20):
    settings = load_runtime_config()
    focus_categories = parse_focus_categories(getattr(project, "category_focus_json", None))
    project_feed_entries = _parse_feed_config(project)

    products = _fetch_entries(project_feed_entries, limit_per_source)
    if not products:
        products = _fetch_entries(_global_feed_entries(settings), limit_per_source)
    if focus_categories:
        products = [product for product in products if product_matches_focus(product, focus_categories)]

    if not products and getattr(settings, "marketplace_demo_mode", False):
        products.extend(
            product
            for product in get_demo_products(project.slug)
            if not focus_categories or product_matches_focus(product, focus_categories)
        )
    return products
