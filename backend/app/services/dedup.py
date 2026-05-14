from __future__ import annotations

import re
from difflib import SequenceMatcher


VARIANT_PATTERNS = [
    r"\b\d+\s?(gb|tb|mb|hz|w|mah|mm|cm|inch|in)\b",
    r"\b\d+\s?шт\b",
    r"\b(black|white|gray|silver|red|blue|green|pink)\b",
]


def normalize_text(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    for pattern in VARIANT_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_dedup_key(title: str, brand: str | None, category: str) -> str:
    parts = [normalize_text(brand or ""), normalize_text(title), normalize_text(category)]
    return "|".join(part for part in parts if part)


def build_family_key(title: str, brand: str | None, category: str) -> str:
    base = normalize_text(title)
    base = re.sub(r"\b\d+\b", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return "|".join(part for part in [normalize_text(brand or ""), base, normalize_text(category)] if part)


def is_duplicate(existing: list[dict[str, str]], title: str, brand: str | None, category: str) -> bool:
    candidate_key = build_dedup_key(title, brand, category)
    family_key = build_family_key(title, brand, category)
    candidate_norm = normalize_text(title)
    for item in existing:
        stored_title = item.get("title", "")
        stored_brand = item.get("brand")
        stored_category = item.get("category", "general")
        if candidate_key == build_dedup_key(stored_title, stored_brand, stored_category):
            return True
        if family_key == build_family_key(stored_title, stored_brand, stored_category):
            return True
        if SequenceMatcher(None, candidate_norm, normalize_text(stored_title)).ratio() >= 0.92:
            return True
    return False

