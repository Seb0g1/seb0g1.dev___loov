from __future__ import annotations

import base64
import io
import logging
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings

logger = logging.getLogger(__name__)


DEFAULT_ACCENT = (255, 174, 66)
DEFAULT_SECONDARY = (77, 124, 255)
TEXT = (245, 247, 250)
MUTED = (170, 177, 191)
BG = (12, 16, 26)
PANEL = (20, 26, 40)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _hex_to_rgb(value: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not value or not isinstance(value, str) or not value.startswith("#") or len(value) != 7:
        return fallback
    try:
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    except Exception:
        return fallback


async def _load_image(url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        if Path(url).exists():
            return Image.open(url).convert("RGBA")
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGBA")
            return image
    except Exception as exc:
        logger.warning("Image download failed for %s: %s", url, exc)
        return None


def build_image_prompt(product: dict, project: dict | None = None) -> str:
    project_name = (project or {}).get("name") if project else "Telegram channel"
    title = product.get("title", "Product")
    brand = product.get("brand") or ""
    category = product.get("category") or ""
    description = product.get("description") or ""
    return (
        f"Premium e-commerce hero image for {project_name}. "
        f"Product: {title}. Brand: {brand}. Category: {category}. "
        f"Style: dark premium editorial, clean composition, centered subject, realistic lighting, "
        f"no text, no logos, no captions, no watermark, no UI, no collage. "
        f"Use the product look and feel from the reference image when provided. "
        f"Description: {description}"
    )


async def _generate_codex_sale_reference_image(product: dict, project: dict | None = None) -> Image.Image | None:
    settings = get_settings()
    if settings.image_engine != "codex_sale" or not settings.codex_sale_api_key:
        return None

    prompt = build_image_prompt(product, project)
    source_url = (product.get("images") or [None])[0]
    source_image = await _load_image(source_url)
    timeout = max(int(getattr(settings, "codex_sale_timeout_seconds", 300) or 300), 60)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if settings.image_generation_mode == "image_to_image" and source_image is not None:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    source_path = Path(tmp.name)
                    source_image.save(source_path)
                try:
                    with source_path.open("rb") as image_file:
                        response = await client.post(
                            f"{settings.codex_sale_base_url.rstrip('/')}/images/edits",
                            headers={"Authorization": f"Bearer {settings.codex_sale_api_key}"},
                            files={
                                "image": ("source.png", image_file, "image/png"),
                            },
                            data={
                                "model": settings.codex_sale_image_model,
                                "prompt": prompt,
                                "size": settings.codex_sale_image_size,
                            },
                        )
                finally:
                    try:
                        source_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            else:
                response = await client.post(
                    f"{settings.codex_sale_base_url.rstrip('/')}/images/generations",
                    headers={
                        "Authorization": f"Bearer {settings.codex_sale_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.codex_sale_image_model,
                        "prompt": prompt,
                        "size": settings.codex_sale_image_size,
                    },
                )

            response.raise_for_status()
            payload = response.json()
            data = (payload.get("data") or [{}])[0]
            if data.get("b64_json"):
                return Image.open(io.BytesIO(base64.b64decode(data["b64_json"]))).convert("RGBA")
            if data.get("url"):
                downloaded = await _load_image(data["url"])
                return downloaded
    except Exception as exc:
        logger.exception("Codex Sale image generation failed: %s", exc)
    return None


def _fit_image(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    copy = image.copy().convert("RGBA")
    copy.thumbnail(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", target, (0, 0, 0, 0))
    x = (target[0] - copy.width) // 2
    y = (target[1] - copy.height) // 2
    canvas.paste(copy, (x, y), copy if copy.mode == "RGBA" else None)
    return canvas


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


async def render_poster(
    product: dict,
    project: dict | None = None,
    output_name: str | None = None,
    variant: int = 0,
) -> str:
    settings = get_settings()
    canvas = Image.new("RGBA", (1400, 1400), BG)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((48, 48, 1352, 1352), radius=36, fill=PANEL)
    draw.rounded_rectangle((60, 60, 1340, 1340), radius=30, outline=(32, 40, 60), width=2)

    accent = DEFAULT_ACCENT if variant % 2 == 0 else DEFAULT_SECONDARY
    logo_text = "Техно Халява"
    tagline = "Товар отобран по выгоде и актуальности"
    project_slug = "tehno_halyava"

    if project:
        accent = _hex_to_rgb(project.get("accent_color"), accent)
        secondary = _hex_to_rgb(project.get("accent_secondary"), DEFAULT_SECONDARY)
        if variant % 2 == 1:
            accent = secondary
        logo_text = project.get("logo_text") or project.get("name") or logo_text
        tagline = project.get("tagline") or tagline
        project_slug = (project.get("slug") or project_slug).replace("-", "")

    draw.rounded_rectangle((76, 76, 330, 170), radius=24, fill=accent)
    draw.text((106, 108), logo_text, fill=(10, 12, 18), font=_font(40, True))

    title = product.get("title", "Товар дня")
    lines = _wrap(draw, title, _font(56, True), 640)
    y = 260
    for line in lines[:4]:
        draw.text((88, y), line, fill=TEXT, font=_font(56, True))
        y += 68

    price = product.get("price", 0)
    market_price = product.get("market_price")
    discount = product.get("discount_percent")
    price_text = f"{price:,.0f} ₽".replace(",", " ")
    draw.rounded_rectangle((88, 590, 510, 720), radius=28, fill=(255, 255, 255))
    draw.text((120, 618), price_text, fill=(10, 12, 18), font=_font(58, True))
    if market_price:
        draw.text((88, 745), f"Было {market_price:,.0f} ₽".replace(",", " "), fill=MUTED, font=_font(30))
    if discount:
        draw.rounded_rectangle((520, 590, 690, 670), radius=22, fill=accent)
        draw.text((556, 613), f"-{int(discount)}%", fill=(10, 12, 18), font=_font(34, True))

    rating = product.get("rating")
    reviews = product.get("reviews_count")
    tags = []
    if rating:
        tags.append(f"Рейтинг {rating:.1f}")
    if reviews:
        tags.append(f"{reviews} отзывов")
    if product.get("stock_count"):
        tags.append("В наличии")
    tag_y = 810
    for idx, tag in enumerate(tags[:3]):
        box = (88 + idx * 250, tag_y, 318 + idx * 250, tag_y + 74)
        draw.rounded_rectangle(box, radius=20, fill=(24, 31, 46))
        draw.text((box[0] + 24, box[1] + 22), tag, fill=TEXT, font=_font(28))

    source_image = await _generate_codex_sale_reference_image(product, project)
    if source_image is None:
        source_image = await _load_image((product.get("images") or [None])[0])
    image_area = (760, 190, 1288, 1180)
    draw.rounded_rectangle(image_area, radius=32, fill=(15, 19, 30))
    if source_image:
        fitted = _fit_image(source_image, (480, 920))
        canvas.paste(fitted, (800, 220), fitted)
    else:
        placeholder = Image.new("RGBA", (480, 920), (32, 40, 60))
        ph_draw = ImageDraw.Draw(placeholder)
        ph_draw.text((130, 430), "PHOTO", fill=MUTED, font=_font(48, True))
        canvas.paste(placeholder, (800, 220), placeholder)

    draw.text((88, 1280), tagline, fill=MUTED, font=_font(28))
    draw.text((1100, 1280), f"#{project_slug}", fill=accent, font=_font(28, True))

    result_name = output_name or f"poster_{variant}.png"
    output_path = settings.generated_dir / result_name
    canvas = canvas.filter(ImageFilter.SHARPEN)
    canvas.save(output_path)
    return str(output_path)
