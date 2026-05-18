from __future__ import annotations

import re
from html import escape
from typing import Any
from urllib.parse import quote_plus


MARKETPLACE_EMOJI_IDS = {
    "yandex_market": "5278382921223261526",
    "ozon": "5301057891824843953",
    "wildberries": "5368561648002949851",
}

MARKETPLACE_LABELS = {
    "yandex_market": "Яндекс Маркет",
    "ozon": "Ozon",
    "wildberries": "WB",
}

MARKETPLACE_FALLBACK_EMOJIS = {
    "yandex_market": "🟡",
    "ozon": "🔵",
    "wildberries": "🟣",
}


def normalize_marketplace(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"ym", "yandex", "yandexmarket", "yandex_market"}:
        return "yandex_market"
    if normalized in {"wb", "wildberries"}:
        return "wildberries"
    if normalized == "ozon":
        return "ozon"
    return normalized


def format_price_from(value: float | int | None) -> str:
    amount = float(value or 0)
    return f"от: {amount:,.0f}р.".replace(",", " ")


def product_search_query(title: str | None, brand: str | None = None) -> str:
    clean_title = str(title or "").strip()
    clean_brand = str(brand or "").strip()
    if clean_brand and clean_title.lower().startswith(clean_brand.lower()):
        raw = clean_title
    else:
        raw = " ".join(part for part in [clean_brand, clean_title] if part).strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw[:180]


def marketplace_search_url(marketplace: str, query: str) -> str:
    encoded = quote_plus(query)
    if marketplace == "ozon":
        return f"https://www.ozon.ru/search/?text={encoded}"
    if marketplace == "wildberries":
        return f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded}"
    if marketplace == "yandex_market":
        return f"https://market.yandex.ru/search?text={encoded}"
    return ""


def build_marketplace_links(product: dict | Any) -> dict[str, str]:
    if isinstance(product, dict):
        source = normalize_marketplace(product.get("source"))
        title = product.get("title")
        brand = product.get("brand")
        source_url = product.get("url") or product.get("affiliate_url")
        characteristics = product.get("characteristics") or {}
    else:
        source = normalize_marketplace(getattr(product, "source", ""))
        title = getattr(product, "title", "")
        brand = getattr(product, "brand", "")
        source_url = getattr(product, "url", None) or getattr(product, "affiliate_url", None)
        characteristics = {}

    existing = characteristics.get("marketplace_links") if isinstance(characteristics, dict) else None
    links = dict(existing) if isinstance(existing, dict) else {}
    query = product_search_query(title, brand)
    for marketplace in ("yandex_market", "ozon", "wildberries"):
        if source == marketplace and source_url:
            links[marketplace] = source_url
        elif marketplace not in links and query:
            links[marketplace] = marketplace_search_url(marketplace, query)
    return {key: value for key, value in links.items() if value}


def custom_emoji_html(marketplace: str) -> str:
    emoji_id = MARKETPLACE_EMOJI_IDS[marketplace]
    fallback = MARKETPLACE_FALLBACK_EMOJIS[marketplace]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def build_marketplace_buttons(product: dict | Any) -> list[dict[str, str]]:
    links = build_marketplace_links(product)
    buttons: list[dict[str, str]] = []
    for marketplace in ("yandex_market", "ozon", "wildberries"):
        url = links.get(marketplace)
        if url:
            buttons.append({"text": MARKETPLACE_LABELS[marketplace], "url": url})
    return buttons


def build_marketplace_footer(product: dict | Any) -> str:
    if isinstance(product, dict):
        price = product.get("price")
    else:
        price = getattr(product, "price", None)
    links = build_marketplace_links(product)
    lines = [f"<b>Актуальная цена:</b> {format_price_from(price)}"]
    for marketplace in ("yandex_market", "ozon", "wildberries"):
        if marketplace in links:
            lines.append(f'{custom_emoji_html(marketplace)} <a href="{escape(links[marketplace], quote=True)}">{MARKETPLACE_LABELS[marketplace]}</a>')
    return "\n".join(lines)
