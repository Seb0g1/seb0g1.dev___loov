from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

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


def _feed_entry(marketplace: Any, url: Any, category: Any = "") -> dict[str, str] | None:
    normalized_marketplace = _normalize_marketplace(marketplace)
    normalized_url = str(url or "").strip()
    if not normalized_marketplace or not normalized_url:
        return None
    return {
        "marketplace": normalized_marketplace,
        "url": normalized_url,
        "category": str(category or "").strip(),
    }


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
                        entry = _feed_entry(marketplace, item.get("url"), item.get("category") or item.get("label"))
                    else:
                        entry = _feed_entry(marketplace, item)
                    if entry:
                        entries.append(entry)
            elif isinstance(value, dict):
                entry = _feed_entry(marketplace, value.get("url"), value.get("category") or value.get("label"))
                if entry:
                    entries.append(entry)
            else:
                entry = _feed_entry(marketplace, value)
                if entry:
                    entries.append(entry)
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            entry = _feed_entry(
                item.get("marketplace") or item.get("source"),
                item.get("url") or item.get("feed_url"),
                item.get("category") or item.get("label"),
            )
            if entry:
                entries.append(entry)
    return entries


def _global_feed_entries(settings) -> list[dict[str, str]]:
    rows = [
        _feed_entry("ozon", getattr(settings, "ozon_feed_url", ""), ""),
        _feed_entry("wildberries", getattr(settings, "wildberries_feed_url", ""), ""),
        _feed_entry("yandex_market", getattr(settings, "yandex_market_feed_url", ""), ""),
    ]
    return [row for row in rows if row]


def _fetch_entries(entries: list[dict[str, str]], limit_per_source: int):
    products = []
    seen_urls_by_marketplace: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        marketplace = entry["marketplace"]
        feed_url = entry["url"]
        if feed_url in seen_urls_by_marketplace[marketplace]:
            continue
        seen_urls_by_marketplace[marketplace].add(feed_url)
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
    return fetcher(limit, feed_url, category)


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
