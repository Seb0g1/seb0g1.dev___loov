from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Product
from app.services.marketplace_links import build_marketplace_links, normalize_marketplace
from app.services.marketplaces.common import DEFAULT_HEADERS

logger = logging.getLogger(__name__)


PRICE_RE = re.compile(r"(?:от\s*)?(\d[\d\s\u00a0]{0,10})(?:[,.]\d+)?\s*(?:₽|р\.?|руб\.?)", re.IGNORECASE)


@dataclass
class LiveProductData:
    price: float | None = None
    market_price: float | None = None
    rating: float | None = None
    reviews_count: int | None = None
    text: str = ""


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
    cleaned = re.sub(r"[^\d]", "", str(value))
    try:
        return int(cleaned)
    except ValueError:
        return None


def _bad_price_context(context: str, near: str) -> bool:
    lowered = near.lower()
    if re.search(r"(\d+\s*[×xх]\s*\d+|[×xх]\s*\d+)", near.lower()):
        return True
    return any(
        marker in lowered
        for marker in (
            "платеж",
            "платёж",
            "рассроч",
            "месяц",
            "мес",
            "балл",
            "бонус",
            "кешб",
            "достав",
            "ремонт",
            "замена",
        )
    )


def parse_live_product_data(text: str) -> LiveProductData:
    prices: list[float] = []
    for match in PRICE_RE.finditer(text or ""):
        start, end = match.span()
        context = text[max(0, start - 32) : min(len(text), end + 32)]
        near = text[max(0, start - 8) : min(len(text), end + 8)]
        if _bad_price_context(context, near):
            continue
        value = _safe_float(match.group(1))
        if value is None or value < 20:
            continue
        if value not in prices:
            prices.append(value)

    current = prices[0] if prices else None
    market = None
    if current:
        for value in prices[1:8]:
            if value > current:
                market = value
                break

    rating = None
    rating_match = re.search(r"(?<!\d)([1-5][,.]\d)(?!\d)", text or "")
    if rating_match:
        rating = _safe_float(rating_match.group(1))

    reviews_count = None
    reviews_match = re.search(r"(\d[\d\s\u00a0]*)\s*(?:отзыв|оценк)", text or "", re.IGNORECASE)
    if reviews_match:
        reviews_count = _safe_int(reviews_match.group(1))

    return LiveProductData(price=current, market_price=market, rating=rating, reviews_count=reviews_count, text=text or "")


def _stealth_script() -> str:
    return """
    (() => {
      const define = (target, key, value) => {
        try {
          Object.defineProperty(target, key, { get: () => value, configurable: true });
        } catch (error) {
          void error;
        }
      };
      define(navigator, 'webdriver', undefined);
      define(navigator, 'languages', ['ru-RU', 'ru', 'en-US', 'en']);
      define(navigator, 'platform', 'Win32');
      define(navigator, 'hardwareConcurrency', 8);
      define(navigator, 'deviceMemory', 8);
    })();
    """


def _open_product_page(url: str, screenshot_path: str | None = None) -> tuple[str, str | None]:
    from playwright.sync_api import sync_playwright

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
            timezone_id="Europe/Moscow",
            color_scheme="dark",
            viewport={"width": 1365, "height": 768},
            device_scale_factor=1,
            extra_http_headers={"Accept-Language": DEFAULT_HEADERS["Accept-Language"]},
        )
        page = context.new_page()
        page.add_init_script(_stealth_script())
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=12000)
        except Exception:
            pass
        page.wait_for_timeout(2500)
        try:
            page.locator("text=Понятно").first.click(timeout=1000)
        except Exception:
            pass
        try:
            page.locator("text=Закрыть").first.click(timeout=1000)
        except Exception:
            pass
        text = page.locator("body").inner_text(timeout=10000)
        saved_path = None
        if screenshot_path:
            target = Path(screenshot_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target), full_page=False)
            saved_path = str(target)
        browser.close()
        return text, saved_path


async def fetch_live_product_data(url: str | None) -> LiveProductData:
    if not url:
        return LiveProductData()
    try:
        text, _ = await asyncio.to_thread(_open_product_page, url, None)
        return parse_live_product_data(text)
    except Exception as exc:
        logger.warning("Live product price check failed for %s: %s", url, exc)
        return LiveProductData()


def fetch_live_product_data_sync(url: str | None) -> LiveProductData:
    if not url:
        return LiveProductData()
    try:
        text, _ = _open_product_page(url, None)
        return parse_live_product_data(text)
    except Exception as exc:
        logger.warning("Live product price check failed for %s: %s", url, exc)
        return LiveProductData()


async def capture_product_screenshot(url: str | None, output_path: str | Path) -> str | None:
    if not url:
        return None
    try:
        _, saved_path = await asyncio.to_thread(_open_product_page, url, str(output_path))
        return saved_path
    except Exception as exc:
        logger.warning("Product screenshot failed for %s: %s", url, exc)
        return None


def _load_characteristics(product: Product) -> dict:
    try:
        value = json.loads(product.characteristics_json or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _save_characteristics(product: Product, data: dict) -> None:
    product.characteristics_json = json.dumps(data, ensure_ascii=False)


async def refresh_product_live_data(db: Session, product: Product) -> Product:
    if not product.url:
        return product
    source = normalize_marketplace(product.source)
    if source not in {"yandex_market", "ozon", "wildberries"}:
        return product

    live = await fetch_live_product_data(product.url)
    characteristics = _load_characteristics(product)
    characteristics["marketplace_links"] = build_marketplace_links(
        {
            "source": product.source,
            "title": product.title,
            "brand": product.brand,
            "url": product.url,
            "characteristics": characteristics,
        }
    )
    characteristics["live_price_checked_at"] = datetime.utcnow().isoformat()
    characteristics["live_price_verified"] = bool(live.price)

    if live.price:
        product.price = live.price
    if live.market_price and live.price and live.market_price > live.price:
        product.market_price = live.market_price
        product.discount_percent = round((live.market_price - live.price) / live.market_price * 100, 1)
    if live.rating:
        product.rating = live.rating
    if live.reviews_count:
        product.reviews_count = live.reviews_count
    _save_characteristics(product, characteristics)
    db.flush()
    return product
