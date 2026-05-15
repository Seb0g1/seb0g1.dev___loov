from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from app.services.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)


STYLE_GUIDES = {
    "short": "Короткий Telegram-пост на русском, 2-4 коротких абзаца, акцент на цене и выгоде.",
    "selling": "Продающий Telegram-пост на русском, но без агрессии. Мягкий CTA и ясная выгода.",
    "expert": "Экспертный, лаконичный и полезный стиль. Объясни, почему это предложение хорошее.",
    "premium": "Премиальный стиль с ощущением ценности и качества. Без пафоса и без выдумок.",
    "bundle": "Пост-подборка. Покажи несколько преимуществ и уместную структуру списка.",
    "comparison": "Сравнительный стиль: объясни, чем товар выигрывает по цене и характеристикам.",
}


@dataclass
class GenerationResult:
    text: str
    provider: str
    prompt: str


def build_prompt(product: dict, style: str, project: dict | None = None) -> str:
    guide = STYLE_GUIDES.get(style, STYLE_GUIDES["short"])
    payload = {
        "title": product.get("title"),
        "brand": product.get("brand"),
        "price": product.get("price"),
        "market_price": product.get("market_price"),
        "discount_percent": product.get("discount_percent"),
        "rating": product.get("rating"),
        "reviews_count": product.get("reviews_count"),
        "stock_count": product.get("stock_count"),
        "category": product.get("category"),
        "description": product.get("description"),
        "characteristics": product.get("characteristics") or {},
    }
    project_text = ""
    if project:
        project_text = (
            f"Проект: {project.get('name')}.\n"
            f"Ниша: {project.get('niche')}.\n"
            f"Тон: {project.get('tagline') or project.get('description') or project.get('name')}.\n"
        )
    return (
        f"{project_text}"
        "Ты пишешь пост для Telegram-канала. Не выдумывай характеристики. "
        "Используй только данные из JSON. Если характеристика неизвестна, не упоминай её.\n"
        f"Стиль: {guide}\n"
        f"Данные товара:\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "Формат: заголовок, 2-4 абзаца, затем мягкий CTA. "
        "Добавь цену и кратко объясни выгоду покупки."
    )


def fallback_text(product: dict, style: str, project: dict | None = None) -> str:
    title = product.get("title", "Товар")
    price = product.get("price", 0)
    market_price = product.get("market_price")
    discount = product.get("discount_percent")
    rating = product.get("rating")
    reviews = product.get("reviews_count")
    lead = project.get("name") if project else "Товар дня"
    lines = [f"{lead}: {title}"]
    if discount and market_price:
        lines.append(f"Сейчас стоит {price:,.0f} ₽ вместо {market_price:,.0f} ₽".replace(",", " "))
    else:
        lines.append(f"Цена: {price:,.0f} ₽".replace(",", " "))
    extras = []
    if rating:
        extras.append(f"рейтинг {rating:.1f}")
    if reviews:
        extras.append(f"{reviews} отзывов")
    if extras:
        lines.append(", ".join(extras).capitalize())
    if style in {"comparison", "expert"}:
        lines.append("Это хороший вариант, если нужен понятный баланс цены и характеристик.")
    elif style == "premium":
        lines.append("Выбор для тех, кто хочет аккуратный и достойный вариант без переплаты.")
    elif style == "bundle":
        lines.append("Сильный вариант для подборки выгодных покупок.")
    else:
        lines.append("Если давно присматривались к такой покупке, сейчас момент выглядит удачно.")
    lines.append("Ссылка и детали - в кнопке ниже.")
    return "\n\n".join(lines)


async def generate_text(product: dict, style: str = "short", project: dict | None = None) -> GenerationResult:
    settings = load_runtime_config()
    prompt = build_prompt(product, style, project)
    provider = "fallback"

    if settings.text_engine == "openrouter" and settings.openrouter_api_key:
        try:
            timeout = max(int(getattr(settings, "openrouter_text_timeout_seconds", 180) or 180), 30)
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            if settings.openrouter_site_url:
                headers["HTTP-Referer"] = settings.openrouter_site_url
            if settings.openrouter_site_name:
                headers["X-OpenRouter-Title"] = settings.openrouter_site_name
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": settings.openrouter_text_model,
                        "messages": [
                            {"role": "system", "content": "Ты пишешь продающие, но честные посты на русском."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": int(getattr(settings, "openrouter_text_max_tokens", 900) or 900),
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"].strip()
                provider = f"openrouter:{settings.openrouter_text_model}"
                return GenerationResult(text=text, provider=provider, prompt=prompt)
        except Exception as exc:
            logger.exception("OpenRouter text generation failed: %s", exc)

    if settings.text_engine == "ollama":
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": [
                            {"role": "system", "content": "Ты пишешь честные и продающие посты на русском."},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                    },
                )
                response.raise_for_status()
                data = response.json()
                text = data["message"]["content"].strip()
                provider = f"ollama:{settings.ollama_model}"
                return GenerationResult(text=text, provider=provider, prompt=prompt)
        except Exception as exc:
            logger.exception("Ollama text generation failed: %s", exc)

    text = fallback_text(product, style, project)
    return GenerationResult(text=text, provider=provider, prompt=prompt)
