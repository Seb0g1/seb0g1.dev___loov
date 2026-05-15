from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from lxml import etree
from lxml import html as lxml_html

from app.services.marketplaces.base import MarketplaceProduct


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

PRICE_RE = re.compile(r"(\d[\d\s\u00a0]{1,})(?:[,.]\d+)?\s*(?:\u20bd|руб\.?|р\b)", re.IGNORECASE)
RATING_RE = re.compile(r"(?<!\d)([1-5][,.]\d)(?!\d)")
REVIEWS_RE = re.compile(r"(\d[\d\s\u00a0]*)\s*(?:отзыв|review)", re.IGNORECASE)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d,.\-]", "", str(value)).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


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


def _list_images(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        url = value.get("url") or value.get("src") or value.get("contentUrl")
        return [str(url)] if url else []
    if isinstance(value, list):
        images: list[str] = []
        for item in value:
            images.extend(_list_images(item))
        return images
    return []


def _stable_source_id(record: dict[str, Any]) -> str:
    explicit = (
        record.get("source_id")
        or record.get("id")
        or record.get("sku")
        or record.get("product_id")
        or record.get("offer_id")
        or record.get("productId")
    )
    if explicit:
        return str(explicit)
    seed = str(record.get("url") or record.get("link") or record.get("name") or record.get("title") or record)
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:18]


def _merge_structured_record(record: dict[str, Any]) -> dict[str, Any]:
    merged = dict(record)

    item = merged.get("item")
    if isinstance(item, dict):
        merged = {**item, **merged}

    brand = merged.get("brand")
    if isinstance(brand, dict):
        merged["brand"] = brand.get("name") or brand.get("title") or brand.get("@id") or brand.get("brand") or ""

    offers = merged.get("offers")
    if isinstance(offers, list) and offers:
        first_offer = offers[0]
        if isinstance(first_offer, dict):
            offers = first_offer
    if isinstance(offers, dict):
        for key in ("price", "priceCurrency", "url", "availability", "lowPrice", "highPrice", "priceSpecification"):
            value = offers.get(key)
            if value not in (None, "", []):
                if key not in merged or merged[key] in (None, "", []):
                    merged[key] = value
        if not merged.get("url"):
            for key in ("url", "@id", "link"):
                value = offers.get(key)
                if value:
                    merged["url"] = value
                    break
        if not merged.get("stock_count"):
            availability = str(offers.get("availability") or "").lower()
            if "instock" in availability or "in_stock" in availability:
                merged["stock_count"] = 1

    aggregate_rating = merged.get("aggregateRating")
    if isinstance(aggregate_rating, dict):
        for key in ("ratingValue", "reviewCount"):
            value = aggregate_rating.get(key)
            if value not in (None, "") and key not in merged:
                merged[key] = value

    image = merged.get("image")
    if image and not merged.get("images"):
        merged["images"] = _list_images(image)

    return merged


def _to_product(source: str, record: dict[str, Any], category_hint: str | None = None) -> MarketplaceProduct:
    record = _merge_structured_record(record)
    aggregate_rating = record.get("aggregateRating") if isinstance(record.get("aggregateRating"), dict) else {}
    price = _safe_float(
        record.get("price")
        or record.get("current_price")
        or record.get("currentPrice")
        or record.get("priceValue")
        or record.get("lowPrice")
        or record.get("amount")
        or (record.get("offers", {}) if isinstance(record.get("offers"), dict) else {}).get("price")
        or (record.get("offers", {}) if isinstance(record.get("offers"), dict) else {}).get("lowPrice")
    )
    market_price = _safe_float(
        record.get("market_price")
        or record.get("old_price")
        or record.get("oldPrice")
        or record.get("price_before_discount")
        or record.get("highPrice")
        or (record.get("offers", {}) if isinstance(record.get("offers"), dict) else {}).get("highPrice")
    )
    category = _clean_text(record.get("category") or record.get("category_name") or record.get("categoryName") or category_hint or "general")
    images = _list_images(record.get("images") or record.get("photos") or record.get("image") or record.get("picture"))
    brand_value = record.get("brand") or record.get("vendor") or record.get("brandName")
    if isinstance(brand_value, dict):
        brand_value = brand_value.get("name") or brand_value.get("title") or brand_value.get("brand")
    return MarketplaceProduct(
        source=source,
        source_id=_stable_source_id(record),
        title=_clean_text(record.get("title") or record.get("name") or record.get("product_name") or record.get("productName") or "Unknown product"),
        brand=_clean_text(brand_value) or None,
        category=category,
        price=price or 0,
        market_price=market_price,
        discount_percent=_safe_float(record.get("discount_percent") or record.get("discount") or record.get("discountPercent")),
        rating=_safe_float(record.get("rating") or record.get("score") or record.get("ratingValue") or aggregate_rating.get("ratingValue")),
        reviews_count=_safe_int(record.get("reviews_count") or record.get("reviews") or record.get("reviewCount") or aggregate_rating.get("reviewCount")),
        stock_count=_safe_int(record.get("stock_count") or record.get("stock") or record.get("stockQuantity") or record.get("quantity")),
        url=record.get("url") or record.get("link"),
        description=record.get("description") or record.get("desc"),
        characteristics=record.get("characteristics") or record.get("attributes") or {},
        images=images,
    )


def _is_product_like(record: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in record}
    type_name = str(record.get("@type") or record.get("type") or "").strip().lower()
    has_name = bool(keys & {"title", "name", "product_name", "productname"})
    has_price = bool(keys & {"price", "current_price", "currentprice", "pricevalue", "lowprice", "amount"})
    has_link = bool(keys & {"url", "link", "href"})
    if type_name == "itemlist":
        return False
    if type_name in {"product", "offer"}:
        return True
    if "offers" in keys and (has_name or has_link):
        return True
    return has_name and (has_price or has_link)


def _walk_records(value: Any, records: list[dict[str, Any]], limit: int) -> None:
    if len(records) >= limit:
        return
    if isinstance(value, dict):
        type_name = str(value.get("@type") or value.get("type") or "").strip().lower()
        if type_name == "itemlist":
            items = value.get("itemListElement")
            if isinstance(items, list):
                _walk_records(items, records, limit)
            return
        if isinstance(value.get("item"), dict):
            _walk_records(value.get("item"), records, limit)
            return
        if isinstance(value.get("itemListElement"), list):
            _walk_records(value.get("itemListElement"), records, limit)
            return
        if _is_product_like(value):
            records.append(value)
            return
        for nested in value.values():
            _walk_records(nested, records, limit)
    elif isinstance(value, list):
        for item in value:
            _walk_records(item, records, limit)
            if len(records) >= limit:
                break


def _records_from_payload(payload: Any, limit: int) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "results", "data", "offers", "products", "cards", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value[:limit] if isinstance(item, dict)]
        records: list[dict[str, Any]] = []
        _walk_records(payload, records, limit)
        return records
    if isinstance(payload, list):
        return [item for item in payload[:limit] if isinstance(item, dict)]
    return []


def _parse_json_products(source: str, text: str, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    try:
        payload = json.loads(text)
    except Exception:
        return []
    products: list[MarketplaceProduct] = []
    for record in _records_from_payload(payload, limit):
        product = _to_product(source, record, category_hint)
        if product.source_id and product.title and product.price > 0:
            products.append(product)
    return products[:limit]


def _node_text(node: etree._Element, names: tuple[str, ...]) -> str:
    for name in names:
        values = node.xpath(f".//*[local-name()='{name}']/text()")
        if values:
            return _clean_text(values[0])
    return ""


def _parse_xml_products(source: str, text: str, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    try:
        root = etree.fromstring(text.encode("utf-8"))
    except Exception:
        return []

    categories = {
        _clean_text(node.get("id")): _clean_text(" ".join(node.itertext()))
        for node in root.xpath("//*[local-name()='category']")
        if node.get("id")
    }

    products: list[MarketplaceProduct] = []
    nodes = root.xpath("//*[local-name()='offer' or local-name()='item']")
    for node in nodes[:limit]:
        category_id = _node_text(node, ("categoryId", "category_id"))
        images = [
            _clean_text(value)
            for value in node.xpath(".//*[local-name()='picture' or local-name()='image' or local-name()='image_link']/text()")
            if _clean_text(value)
        ]
        record = {
            "source_id": node.get("id") or _node_text(node, ("guid", "id")),
            "title": _node_text(node, ("name", "title")),
            "brand": _node_text(node, ("vendor", "brand", "brandName")),
            "category": categories.get(category_id) or category_hint or category_id or "general",
            "price": _node_text(node, ("price", "sale_price")),
            "old_price": _node_text(node, ("oldprice", "old_price", "price_before_discount")),
            "url": _node_text(node, ("url", "link")),
            "description": _node_text(node, ("description",)),
            "images": images,
        }
        product = _to_product(source, record, category_hint)
        if product.source_id and product.title and product.price > 0:
            products.append(product)
    return products


def _script_products(source: str, doc: etree._Element, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    products: list[MarketplaceProduct] = []
    for script in doc.xpath("//script/text()"):
        if len(products) >= limit:
            break
        text = _clean_text(script)
        if not text or ("price" not in text.lower() and "product" not in text.lower()):
            continue
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            continue
        chunk = text[start : end + 1]
        parsed = _parse_json_products(source, chunk, limit - len(products), category_hint)
        products.extend(parsed)
    return products[:limit]


def _is_product_link(source: str, href: str) -> bool:
    normalized = href.lower()
    if source == "ozon":
        return "/product/" in normalized
    if source == "wildberries":
        return "/catalog/" in normalized and ("detail.aspx" in normalized or re.search(r"/catalog/\d+", normalized) is not None)
    if source == "yandex_market":
        return "/product--" in normalized or "/product/" in normalized
    return "/product" in normalized or "/catalog/" in normalized


def _card_text(anchor: etree._Element) -> tuple[str, list[str]]:
    node = anchor
    best = _clean_text(" ".join(anchor.itertext()))
    images: list[str] = []
    for _ in range(5):
        parent = node.getparent()
        if parent is None:
            break
        node = parent
        text = _clean_text(" ".join(node.itertext()))
        if 20 < len(text) < 3000:
            best = text
            images = []
            for img in node.xpath(".//img"):
                src = img.get("src") or img.get("data-src") or img.get("data-original")
                if not src and img.get("srcset"):
                    src = img.get("srcset", "").split(",")[0].split()[0]
                if src:
                    images.append(src)
            break
    return best, images


def _price_values(text: str) -> list[float]:
    values: list[float] = []
    for match in PRICE_RE.findall(text):
        value = _safe_float(match)
        if value is not None:
            values.append(value)
    return values


def _title_from_card(anchor: etree._Element, card_text: str) -> str:
    anchor_text = _clean_text(" ".join(anchor.itertext()))
    if len(anchor_text) > 6 and not PRICE_RE.search(anchor_text):
        return anchor_text[:512]
    for line in re.split(r"[\n\r|•]+", card_text):
        line = _clean_text(line)
        if len(line) > 8 and not PRICE_RE.search(line) and "рейтинг" not in line.lower():
            return line[:512]
    return anchor_text[:512] or "Unknown product"


def _parse_html_products(source: str, page_url: str, text: str, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    try:
        doc = lxml_html.fromstring(text)
    except Exception:
        return []

    products = _script_products(source, doc, limit, category_hint)
    if len(products) >= limit:
        return products[:limit]

    seen: set[str] = {product.url or product.source_id for product in products}
    for anchor in doc.xpath("//a[@href]"):
        href = anchor.get("href") or ""
        if not _is_product_link(source, href):
            continue
        url = urljoin(page_url, href)
        if url in seen:
            continue
        text_blob, images = _card_text(anchor)
        prices = _price_values(text_blob)
        if not prices:
            continue
        title = _title_from_card(anchor, text_blob)
        rating_match = RATING_RE.search(text_blob)
        reviews_match = REVIEWS_RE.search(text_blob)
        record = {
            "source_id": url,
            "title": title,
            "category": category_hint or "general",
            "price": prices[0],
            "old_price": prices[1] if len(prices) > 1 and prices[1] > prices[0] else None,
            "rating": rating_match.group(1) if rating_match else None,
            "reviews_count": reviews_match.group(1) if reviews_match else None,
            "url": url,
            "images": [urljoin(page_url, image) for image in images],
        }
        product = _to_product(source, record, category_hint)
        if product.source_id and product.title and product.price > 0:
            products.append(product)
            seen.add(url)
        if len(products) >= limit:
            break
    return products[:limit]


def _render_html_with_browser(feed_url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=DEFAULT_HEADERS["User-Agent"],
                locale="ru-RU",
                viewport={"width": 1440, "height": 1100},
            )
            page = context.new_page()
            page.goto(feed_url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2500)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return ""


def _parse_feed_text(source: str, feed_url: str, text: str, content_type: str, limit: int, category_hint: str | None) -> list[MarketplaceProduct]:
    stripped = text.strip()
    if not stripped:
        return []

    content_type = content_type.lower()
    if "json" in content_type or stripped.startswith("{") or stripped.startswith("["):
        products = _parse_json_products(source, stripped, limit, category_hint)
        if products:
            return products

    if "xml" in content_type or stripped.startswith("<?xml") or stripped.startswith("<yml_catalog") or stripped.startswith("<rss"):
        products = _parse_xml_products(source, stripped, limit, category_hint)
        if products:
            return products

    if "<html" in stripped.lower() or "<!doctype" in stripped.lower() or "<script" in stripped.lower():
        return _parse_html_products(source, feed_url, stripped, limit, category_hint)

    return []


def fetch_json_feed(source: str, feed_url: str | None, limit: int = 20, category_hint: str | None = None) -> list[MarketplaceProduct]:
    if not feed_url:
        return []

    products: list[MarketplaceProduct] = []
    text = ""
    content_type = ""
    try:
        response = httpx.get(feed_url, timeout=30, follow_redirects=True, headers=DEFAULT_HEADERS)
        text = response.text
        content_type = response.headers.get("content-type", "")
        products = _parse_feed_text(source, str(response.url), text, content_type, limit, category_hint)
    except Exception:
        products = []

    if products:
        return products[:limit]

    rendered = _render_html_with_browser(feed_url)
    if rendered and rendered != text:
        return _parse_html_products(source, feed_url, rendered, limit, category_hint)

    return []


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
