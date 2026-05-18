from __future__ import annotations

import base64
import io
import logging
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings
from app.services.runtime_config import load_runtime_config

logger = logging.getLogger(__name__)


DEFAULT_ACCENT = (255, 174, 66)
DEFAULT_SECONDARY = (77, 124, 255)
TEXT = (245, 247, 250)
MUTED = (170, 177, 191)
BG = (12, 16, 26)
INK = (9, 12, 18)

FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    cache_key = (size, bold)
    if cache_key in FONT_CACHE:
        return FONT_CACHE[cache_key]

    candidates = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), size=size)
                FONT_CACHE[cache_key] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    FONT_CACHE[cache_key] = font
    return font


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
        normalized_url = str(url).strip()
        if normalized_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(normalized_url)
                response.raise_for_status()
                image = Image.open(io.BytesIO(response.content)).convert("RGBA")
                return image

        if Path(normalized_url).exists():
            return Image.open(normalized_url).convert("RGBA")
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
    settings = load_runtime_config()
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


def _cover_image(image: Image.Image, target: tuple[int, int]) -> Image.Image:
    copy = image.copy().convert("RGBA")
    scale = max(target[0] / copy.width, target[1] / copy.height)
    resized = copy.resize((max(1, int(copy.width * scale)), max(1, int(copy.height * scale))), Image.Resampling.LANCZOS)
    x = (resized.width - target[0]) // 2
    y = (resized.height - target[1]) // 2
    return resized.crop((x, y, x + target[0], y + target[1]))


def _rounded_paste(canvas: Image.Image, image: Image.Image, box: tuple[int, int, int, int], radius: int) -> None:
    width = box[2] - box[0]
    height = box[3] - box[1]
    image = image.resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
    canvas.paste(image, (box[0], box[1]), mask)


def _format_price(value: float | int | None) -> str:
    amount = float(value or 0)
    return f"{amount:,.0f} ₽".replace(",", " ")


def _format_int(value: float | int | None) -> str:
    amount = int(float(value or 0))
    return f"{amount:,}".replace(",", " ")


def _blend(first: tuple[int, int, int], second: tuple[int, int, int], ratio: float) -> tuple[int, int, int]:
    return tuple(int(first[index] * (1 - ratio) + second[index] * ratio) for index in range(3))


def _draw_vertical_gradient(canvas: Image.Image, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    pixels = canvas.load()
    height = canvas.height
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = _blend(top, bottom, ratio)
        for x in range(canvas.width):
            pixels[x, y] = (*color, 255)


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


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_lines: int = 3,
    line_gap: int = 8,
) -> int:
    lines = _wrap(draw, text, font, max_width)
    y = xy[1]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        tail = lines[-1]
        while tail and draw.textbbox((0, 0), f"{tail}...", font=font)[2] > max_width:
            tail = tail[:-1].rstrip()
        lines[-1] = f"{tail}..." if tail else lines[-1]
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text((xy[0], y), line, fill=fill, font=font)
        y += bbox[3] - bbox[1] + line_gap
    return y


def _ellipsize(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = text.strip()
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), f"{text}...", font=font)[2] > max_width:
        text = text[:-1].rstrip()
    return f"{text}..." if text else ""


def _draw_chip(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, fill: tuple[int, int, int], outline: tuple[int, int, int] | None = None) -> None:
    draw.rounded_rectangle(box, radius=24, fill=fill, outline=outline)
    bbox = draw.textbbox((0, 0), text, font=_font(30, True))
    draw.text(
        (box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) // 2, box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) // 2 - 2),
        text,
        fill=TEXT,
        font=_font(30, True),
    )


async def render_poster(
    product: dict,
    project: dict | None = None,
    output_name: str | None = None,
    variant: int = 0,
) -> str:
    settings = get_settings()
    canvas = Image.new("RGBA", (1400, 1400), BG)
    _draw_vertical_gradient(canvas, (9, 13, 22), (17, 23, 36))
    draw = ImageDraw.Draw(canvas)

    accent = DEFAULT_ACCENT if variant % 2 == 0 else DEFAULT_SECONDARY
    logo_text = "Техно Халява"
    tagline = "Товар отобран по выгоде и актуальности"
    project_slug = "tehno_halyava"
    project_name = "Техно Халява"

    if project:
        accent = _hex_to_rgb(project.get("accent_color"), accent)
        secondary = _hex_to_rgb(project.get("accent_secondary"), DEFAULT_SECONDARY)
        if variant % 2 == 1:
            accent = secondary
        project_name = project.get("name") or project_name
        logo_text = project.get("logo_text") or project_name
        tagline = project.get("tagline") or tagline
        project_slug = (project.get("slug") or project_slug).replace("-", "")

    accent_soft = _blend(accent, (255, 255, 255), 0.22)
    accent_dark = _blend(accent, (0, 0, 0), 0.42)

    # Outer frame
    draw.rounded_rectangle((44, 44, 1356, 1356), radius=40, fill=(16, 22, 34), outline=(36, 47, 70), width=2)
    draw.rounded_rectangle((64, 64, 1336, 1336), radius=32, outline=(50, 64, 92), width=1)

    # Product image is the source of truth. AI generation is only a fallback when the feed has no image.
    source_image = await _load_image((product.get("images") or [None])[0])
    if source_image is None:
        source_image = await _generate_codex_sale_reference_image(product, project)

    image_area = (662, 164, 1286, 1128)
    shadow = Image.new("RGBA", (image_area[2] - image_area[0] + 44, image_area[3] - image_area[1] + 44), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle((22, 22, shadow.width - 22, shadow.height - 22), radius=42, fill=(0, 0, 0, 130))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste(shadow, (image_area[0] - 22, image_area[1] - 12), shadow)

    draw.rounded_rectangle(image_area, radius=38, fill=(8, 11, 18), outline=(34, 44, 64), width=2)
    if source_image:
        bg = _cover_image(source_image, (image_area[2] - image_area[0], image_area[3] - image_area[1])).filter(ImageFilter.GaussianBlur(24))
        overlay = Image.new("RGBA", bg.size, (7, 10, 16, 150))
        bg.alpha_composite(overlay)
        _rounded_paste(canvas, bg, image_area, 38)

        fitted = _fit_image(source_image, (560, 760))
        x = image_area[0] + (image_area[2] - image_area[0] - fitted.width) // 2
        y = image_area[1] + (image_area[3] - image_area[1] - fitted.height) // 2
        canvas.paste(fitted, (x, y), fitted)
    else:
        placeholder = Image.new("RGBA", (image_area[2] - image_area[0], image_area[3] - image_area[1]), (18, 24, 38))
        ph_draw = ImageDraw.Draw(placeholder)
        ph_draw.rounded_rectangle((52, 352, placeholder.width - 52, 510), radius=28, fill=(25, 33, 50), outline=(44, 56, 82))
        ph_draw.text((142, 402), "Фото товара", fill=MUTED, font=_font(48, True))
        _rounded_paste(canvas, placeholder, image_area, 38)

    # Header badge
    badge_box = (88, 88, 540, 164)
    draw.rounded_rectangle(badge_box, radius=24, fill=accent)
    logo_font = _font(34 if len(logo_text) <= 18 else 28, True)
    draw.text((114, 111), logo_text[:28], fill=INK, font=logo_font)
    draw.text((88, 190), project_name, fill=accent_soft, font=_font(30, True))

    title = str(product.get("title") or "Товар дня").strip()
    y = _draw_wrapped(draw, title, (88, 238), 520, _font(58, True), TEXT, max_lines=4, line_gap=10)

    brand = product.get("brand")
    if brand:
        y += 14
        draw.text((88, y), str(brand)[:42], fill=MUTED, font=_font(30))

    price = product.get("price", 0)
    market_price = product.get("market_price")
    discount = product.get("discount_percent")

    price_card = (88, 646, 606, 822)
    draw.rounded_rectangle(price_card, radius=32, fill=(246, 248, 252))
    draw.text((124, 676), "Цена сейчас", fill=(68, 76, 90), font=_font(26, True))
    draw.text((122, 712), _format_price(price), fill=INK, font=_font(68, True))
    if market_price:
        draw.text((124, 786), f"обычно {_format_price(market_price)}", fill=(97, 105, 118), font=_font(26))
    if discount:
        discount_box = (430, 672, 574, 732)
        draw.rounded_rectangle(discount_box, radius=20, fill=accent)
        draw.text((462, 686), f"-{int(discount)}%", fill=INK, font=_font(30, True))

    rating = product.get("rating")
    reviews = product.get("reviews_count")
    tags: list[str] = []
    if rating:
        tags.append(f"Рейтинг {float(rating):.1f}")
    if reviews:
        tags.append(f"{_format_int(reviews)} отзывов")
    if product.get("stock_count"):
        tags.append("В наличии")
    chip_y = 860
    chip_x = 88
    for tag in tags[:3]:
        width = max(188, draw.textbbox((0, 0), tag, font=_font(30, True))[2] + 52)
        _draw_chip(draw, (chip_x, chip_y, min(chip_x + width, 606), chip_y + 70), tag, (25, 33, 50), outline=(42, 54, 78))
        chip_y += 86

    cta_box = (88, 1154, 1286, 1278)
    draw.rounded_rectangle(cta_box, radius=34, fill=(11, 16, 26), outline=accent_dark, width=2)
    draw.text((122, 1186), _ellipsize(draw, tagline, _font(36, True), 860), fill=TEXT, font=_font(36, True))
    draw.text((122, 1234), "Ссылка и детали — в кнопке под постом", fill=MUTED, font=_font(26))
    hash_text = f"#{project_slug}"
    hash_bbox = draw.textbbox((0, 0), hash_text, font=_font(30, True))
    draw.text((1260 - (hash_bbox[2] - hash_bbox[0]), 1230), hash_text, fill=accent, font=_font(30, True))

    result_name = output_name or f"poster_{variant}.png"
    output_path = settings.generated_dir / result_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return str(output_path)
