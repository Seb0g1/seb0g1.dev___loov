from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

from app.services.marketplaces.base import MarketplaceProduct
from app.services.marketplaces.common import DEFAULT_HEADERS, fetch_json_feed


WB_SEARCH_ENDPOINT = "https://search.wb.ru/exactmatch/ru/common/v18/search"

SEARCH_ALIASES = {
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


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        cleaned = re.sub(r"[^\d,.\-]", "", str(value)).replace(",", ".")
        if not cleaned:
            return None
        try:
            result = float(cleaned)
        except ValueError:
            return None
    return result / 100 if result >= 10000 else result


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    cleaned = re.sub(r"[^\d]", "", str(value))
    try:
        return int(cleaned)
    except ValueError:
        return None


def _query_from_hint(category_hint: str | None) -> str:
    raw = str(category_hint or "").strip()
    if not raw:
        return ""
    tokens = [item.strip() for item in raw.replace(";", ",").replace("|", ",").replace("\n", ",").split(",") if item.strip()]
    mapped = [SEARCH_ALIASES.get(token.lower(), token) for token in tokens]
    return " ".join(dict.fromkeys(mapped)).strip()


def _query_from_url(feed_url: str | None) -> str:
    if not feed_url:
        return ""
    parsed = urlparse(feed_url)
    params = parse_qs(parsed.query)
    for key in ("query", "search", "text"):
        value = params.get(key)
        if value and value[0].strip():
            return value[0].strip()
    return ""


def _looks_like_wb_search_url(feed_url: str | None) -> bool:
    if not feed_url:
        return False
    host = urlparse(feed_url).netloc.lower()
    return "wildberries.ru" in host or "wb.ru" in host


def _build_search_url(query: str) -> str:
    return (
        f"{WB_SEARCH_ENDPOINT}?appType=1&curr=rub&dest=-1257786&page=1"
        f"&query={quote_plus(query)}&resultset=catalog&sort=popular&spp=30&suppressSpellcheck=false"
    )


def _basket_host(nm_id: int) -> str:
    volume = nm_id // 100000
    if volume <= 143:
        basket = "01"
    elif volume <= 287:
        basket = "02"
    elif volume <= 431:
        basket = "03"
    elif volume <= 719:
        basket = "04"
    elif volume <= 1007:
        basket = "05"
    elif volume <= 1061:
        basket = "06"
    elif volume <= 1115:
        basket = "07"
    elif volume <= 1169:
        basket = "08"
    elif volume <= 1313:
        basket = "09"
    elif volume <= 1601:
        basket = "10"
    elif volume <= 1655:
        basket = "11"
    elif volume <= 1919:
        basket = "12"
    elif volume <= 2045:
        basket = "13"
    elif volume <= 2189:
        basket = "14"
    elif volume <= 2405:
        basket = "15"
    else:
        basket = "16"
    return f"basket-{basket}.wbbasket.ru"


def _image_urls(nm_id: int, pics: int | None) -> list[str]:
    if not nm_id:
        return []
    volume = nm_id // 100000
    part = nm_id // 1000
    count = max(1, min(int(pics or 1), 3))
    return [
        f"https://{_basket_host(nm_id)}/vol{volume}/part{part}/{nm_id}/images/big/{index}.webp"
        for index in range(1, count + 1)
    ]


def _price_from_product(product: dict[str, Any]) -> tuple[float, float | None]:
    current = _safe_float(product.get("salePriceU") or product.get("salePrice") or product.get("sale_price"))
    old = _safe_float(product.get("priceU") or product.get("price") or product.get("basicPriceU"))
    for size in product.get("sizes") or []:
        if not isinstance(size, dict):
            continue
        price = size.get("price")
        if not isinstance(price, dict):
            continue
        current = current or _safe_float(price.get("total") or price.get("product") or price.get("sale"))
        old = old or _safe_float(price.get("basic") or price.get("price"))
        if current:
            break
    return current or 0, old if old and old > (current or 0) else None


def _stock_from_product(product: dict[str, Any]) -> int | None:
    total = 0
    found = False
    for size in product.get("sizes") or []:
        if not isinstance(size, dict):
            continue
        for stock in size.get("stocks") or []:
            if isinstance(stock, dict):
                quantity = _safe_int(stock.get("qty"))
                if quantity is not None:
                    total += quantity
                    found = True
    return total if found else _safe_int(product.get("totalQuantity"))


def _to_product(record: dict[str, Any], category_hint: str | None) -> MarketplaceProduct | None:
    nm_id = _safe_int(record.get("id") or record.get("nmId"))
    title = _clean_text(record.get("name") or record.get("title"))
    if not nm_id or not title:
        return None

    price, market_price = _price_from_product(record)
    if price <= 0:
        return None

    discount_percent = _safe_float(record.get("sale") or record.get("discount"))
    if not discount_percent and market_price and market_price > price:
        discount_percent = round((market_price - price) / market_price * 100, 1)

    return MarketplaceProduct(
        source="wildberries",
        source_id=str(nm_id),
        title=title,
        brand=_clean_text(record.get("brand")) or None,
        category=_clean_text(record.get("subjectName") or record.get("subject") or category_hint or "general"),
        price=price,
        market_price=market_price,
        discount_percent=discount_percent,
        rating=_safe_float(record.get("reviewRating") or record.get("rating")),
        reviews_count=_safe_int(record.get("feedbacks") or record.get("reviews")),
        stock_count=_stock_from_product(record),
        url=f"https://www.wildberries.ru/catalog/{nm_id}/detail.aspx",
        description=title,
        characteristics={},
        images=_image_urls(nm_id, _safe_int(record.get("pics"))),
    )


def _fetch_search_products(query: str, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    if not query:
        return []
    headers = {
        **DEFAULT_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.wildberries.ru",
        "Referer": f"https://www.wildberries.ru/catalog/0/search.aspx?search={quote_plus(query)}",
    }
    response = httpx.get(_build_search_url(query), timeout=25, follow_redirects=True, headers=headers)
    if response.status_code in {401, 403, 429, 498}:
        raise RuntimeError("wildberries blocked by API rate limit or antibot challenge")
    response.raise_for_status()
    payload = response.json()
    products = []
    for record in ((payload.get("data") or {}).get("products") or [])[: limit * 3]:
        if not isinstance(record, dict):
            continue
        product = _to_product(record, category_hint)
        if product:
            products.append(product)
        if len(products) >= limit:
            break
    return products


def fetch_products(limit: int = 20, feed_url: str | None = None, category_hint: str | None = None) -> list[MarketplaceProduct]:
    query = _query_from_url(feed_url) or _query_from_hint(category_hint)
    search_error: Exception | None = None
    if query and (not feed_url or _looks_like_wb_search_url(feed_url)):
        try:
            products = _fetch_search_products(query, limit, category_hint)
            if products:
                return products[:limit]
        except Exception as exc:
            search_error = exc

    if feed_url:
        try:
            products = fetch_json_feed("wildberries", feed_url, limit, category_hint)
            if products:
                return products[:limit]
        except Exception as exc:
            if search_error:
                raise search_error from exc
            raise

    if search_error:
        raise search_error
    return []
