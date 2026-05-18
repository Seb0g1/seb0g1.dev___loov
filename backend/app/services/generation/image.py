from __future__ import annotations

import base64
import hashlib
import io
import logging
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import get_settings
from app.services.live_product import capture_product_screenshot
from app.services.marketplace_links import format_price_from
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
    return format_price_from(value)


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


def _safe_file_token(value: str | None) -> str:
    raw = str(value or "product")
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:18]


def _draw_browser_chrome(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], url: str | None) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=30, fill=(17, 22, 34), outline=(40, 53, 78), width=2)
    draw.rounded_rectangle((x1, y1, x2, y1 + 58), radius=30, fill=(22, 29, 44))
    draw.rectangle((x1, y1 + 30, x2, y1 + 58), fill=(22, 29, 44))
    for index, color in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        draw.ellipse((x1 + 26 + index * 28, y1 + 22, x1 + 42 + index * 28, y1 + 38), fill=color)
    address = str(url or "marketplace").replace("https://", "").replace("http://", "")
    address = address[:86]
    draw.rounded_rectangle((x1 + 132, y1 + 14, x2 - 26, y1 + 46), radius=16, fill=(10, 14, 22), outline=(45, 58, 82))
    draw.text((x1 + 150, y1 + 21), address, fill=(178, 188, 206), font=_font(18))


async def _load_product_screenshot(product: dict, output_name: str | None) -> Image.Image | None:
    settings = get_settings()
    url = product.get("url")
    if not url:
        return None
    token = _safe_file_token(str(product.get("source_id") or product.get("id") or url))
    screenshot_name = f"screenshot_{token}.png" if not output_name else f"{Path(output_name).stem}_page.png"
    screenshot_path = settings.generated_dir / "screenshots" / screenshot_name
    saved = await capture_product_screenshot(url, screenshot_path)
    if not saved:
        return None
    try:
        return Image.open(saved).convert("RGBA")
    except Exception as exc:
        logger.warning("Screenshot open failed for %s: %s", saved, exc)
        return None


async def render_poster(
    product: dict,
    project: dict | None = None,
    output_name: str | None = None,
    variant: int = 0,
) -> str:
    settings = get_settings()
    canvas = Image.new("RGBA", (1400, 920), BG)
    _draw_vertical_gradient(canvas, (8, 12, 20), (17, 23, 36))
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

    # Screenshot is the source of truth: no AI redraw, no invented product.
    screenshot = await _load_product_screenshot(product, output_name)
    if screenshot is None:
        screenshot = await _load_image((product.get("images") or [None])[0])

    frame = (42, 42, 1358, 792)
    _draw_browser_chrome(draw, frame, product.get("url"))
    content_box = (64, 106, 1336, 770)
    if screenshot:
        shot = _cover_image(screenshot, (content_box[2] - content_box[0], content_box[3] - content_box[1]))
        _rounded_paste(canvas, shot, content_box, 18)
    else:
        draw.rounded_rectangle(content_box, radius=18, fill=(18, 24, 38), outline=(44, 56, 82))
        draw.text((562, 405), "Скриншот товара недоступен", fill=MUTED, font=_font(34, True))

    footer = (42, 806, 1358, 884)
    draw.rounded_rectangle(footer, radius=24, fill=(11, 16, 26), outline=accent_dark, width=2)
    draw.rounded_rectangle((66, 826, 174, 864), radius=14, fill=accent)
    logo_font = _font(22 if len(logo_text) <= 18 else 18, True)
    draw.text((84, 834), logo_text[:14], fill=INK, font=logo_font)

    title = _ellipsize(draw, str(product.get("title") or "Товар дня"), _font(30, True), 760)
    draw.text((196, 818), title, fill=TEXT, font=_font(30, True))
    draw.text((196, 854), _ellipsize(draw, tagline, _font(20), 720), fill=accent_soft, font=_font(20))

    price_text = _format_price(product.get("price"))
    price_bbox = draw.textbbox((0, 0), price_text, font=_font(42, True))
    price_x = 1312 - (price_bbox[2] - price_bbox[0])
    draw.text((price_x, 818), price_text, fill=accent, font=_font(42, True))
    hash_text = f"#{project_slug}"
    hash_bbox = draw.textbbox((0, 0), hash_text, font=_font(20, True))
    draw.text((1312 - (hash_bbox[2] - hash_bbox[0]), 862), hash_text, fill=MUTED, font=_font(20, True))

    result_name = output_name or f"poster_{variant}.png"
    output_path = settings.generated_dir / result_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return str(output_path)
