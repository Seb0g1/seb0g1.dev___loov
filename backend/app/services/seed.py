from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AdPackage, AppSetting, Project, ReferralTemplate, SyncStatus


DEFAULT_SETTINGS = {
    "default_style": "short",
    "auto_posting_enabled": "false",
    "theme": "dark-premium",
    "telegram_bot_token": "",
    "telegram_bot_username": "",
    "telegram_admin_id": "",
    "yookassa_shop_id": "",
    "yookassa_secret_key": "",
    "yookassa_return_url": "https://ai.sebog1.ru",
    "cryptobot_api_token": "",
    "cryptobot_asset": "USDT",
    "text_engine": "openrouter",
    "openrouter_api_key": "",
    "openrouter_base_url": "https://openrouter.ai/api/v1",
    "openrouter_text_model": "openrouter/cypher-alpha:free",
    "openrouter_text_timeout_seconds": "180",
    "openrouter_text_max_tokens": "900",
    "openrouter_site_url": "https://ai.sebog1.ru",
    "openrouter_site_name": "Aromat Day",
    "image_engine": "codex_sale",
    "codex_sale_api_key": "",
    "codex_sale_base_url": "https://codex.sale/v1",
    "codex_sale_image_model": "gpt-image-2",
    "codex_sale_image_size": "1024x1024",
    "codex_sale_timeout_seconds": "300",
    "image_generation_mode": "image_to_image",
    "ozon_feed_url": "",
    "wildberries_feed_url": "",
    "yandex_market_feed_url": "",
    "marketplace_demo_mode": "false",
    "import_interval_minutes": "30",
    "publish_interval_minutes": "5",
    "telethon_api_id": "0",
    "telethon_api_hash": "",
    "telethon_session_name": "tehno_halava_verifier",
}

DEFAULT_AD_PACKAGES = [
    {
        "code": "all_channels_24h",
        "name": "Р РµРєР»Р°РјР° РІРѕ РІСЃРµС… РєР°РЅР°Р»Р°С… 24 С‡Р°СЃР°",
        "description": "РџСѓР±Р»РёРєР°С†РёСЏ СЂРµРєР»Р°РјС‹ РІРѕ РІСЃРµС… РїСЂРѕРµРєС‚Р°С… СЃРµС‚Рё РЅР° 24 С‡Р°СЃР°.",
        "amount": 2500,
        "duration_hours": 24,
        "delete_after_hours": 24,
        "sort_order": 1,
    },
    {
        "code": "all_channels_48h",
        "name": "Р РµРєР»Р°РјР° РІРѕ РІСЃРµС… РєР°РЅР°Р»Р°С… 48 С‡Р°СЃРѕРІ",
        "description": "РџСѓР±Р»РёРєР°С†РёСЏ СЂРµРєР»Р°РјС‹ РІРѕ РІСЃРµС… РїСЂРѕРµРєС‚Р°С… СЃРµС‚Рё РЅР° 48 С‡Р°СЃРѕРІ.",
        "amount": 3900,
        "duration_hours": 48,
        "delete_after_hours": 48,
        "sort_order": 2,
    },
    {
        "code": "sticky_story",
        "name": "РСЃС‚РѕСЂРёСЏ Рё Р·Р°РєСЂРµРї",
        "description": "Р РµРєР»Р°РјР° СЃ СѓСЃРёР»РµРЅРЅС‹Рј СЂР°Р·РјРµС‰РµРЅРёРµРј Рё Р·Р°РєСЂРµРїРѕРј РІ РєР°РЅР°Р»Р°С….",
        "amount": 4800,
        "duration_hours": 72,
        "delete_after_hours": 72,
        "sort_order": 3,
    },
]


DEFAULT_PROJECTS = [
    {
        "slug": "uyut-za-kopeiki",
        "name": "РЈСЋС‚ Р·Р° РєРѕРїРµР№РєРё",
        "telegram_channel_url": "https://t.me/yut_za_kopeiki",
        "telegram_channel_id": "@yut_za_kopeiki",
        "niche": "Р’СЃС‘ РґР»СЏ РґРѕРјР°: СѓСЋС‚ Рё РґРµРєРѕСЂ",
        "description": "РџРѕСЃС‚РµР»СЊРЅРѕРµ Р±РµР»СЊРµ, СЃС‚РёР»СЊРЅС‹Рµ Р»Р°РјРїС‹, РѕСЂРіР°РЅР°Р№Р·РµСЂС‹, РїРѕСЃСѓРґР° Рё СЌСЃС‚РµС‚РёРєР° Pinterest-РґРѕРјР°.",
        "tagline": "РЈСЋС‚РЅРѕ, РєСЂР°СЃРёРІРѕ Рё РЅРµРґРѕСЂРѕРіРѕ",
        "accent_color": "#ffae42",
        "accent_secondary": "#4d7cff",
        "logo_text": "РЈР—Рљ",
        "category_focus_json": json.dumps(["bedding", "lamps", "organizers", "tableware"], ensure_ascii=False),
        "feed_config_json": "",
        "sort_order": 1,
    },
    {
        "slug": "zheleznyi-vitamin",
        "name": "Р–РµР»РµР·РЅС‹Р№ Р’РёС‚Р°РјРёРЅ",
        "telegram_channel_url": "https://t.me/zheleznyi_vitamin",
        "telegram_channel_id": "@zheleznyi_vitamin",
        "niche": "РЎРїРѕСЂС‚РїРёС‚ Рё РґРѕР±Р°РІРєРё",
        "description": "РџСЂРѕС‚РµРёРЅ, РІРёС‚Р°РјРёРЅС‹, РєСЂРµР°С‚РёРЅ, РѕРјРµРіР°-3 Рё РІСЃС‘, С‡С‚Рѕ Р±РµСЂСѓС‚ РєР°Р¶РґС‹Р№ РјРµСЃСЏС†.",
        "tagline": "Р–РµР»РµР·Рѕ, РІРёС‚Р°РјРёРЅС‹, СЌРЅРµСЂРіРёСЏ",
        "accent_color": "#7dd3fc",
        "accent_secondary": "#22c55e",
        "logo_text": "Р–Р’",
        "category_focus_json": json.dumps(["protein", "vitamins", "creatine", "omega-3"], ensure_ascii=False),
        "feed_config_json": "",
        "sort_order": 2,
    },
    {
        "slug": "tochka-stilyev",
        "name": "РўРѕС‡РєР° СЃС‚РёР»СЏ",
        "telegram_channel_url": "https://t.me/tochka_stilyev",
        "telegram_channel_id": "@tochka_stilyev",
        "niche": "РљСЂРѕСЃСЃРѕРІРєРё Рё Р±СЂРµРЅРґРѕРІР°СЏ РѕРґРµР¶РґР°",
        "description": "РћСЂРёРіРёРЅР°Р»СЊРЅС‹Рµ РєСЂРѕСЃСЃРѕРІРєРё, РѕРґРµР¶РґР° Рё РїСЂРёРєРѕР»СЊРЅС‹Рµ С€РјРѕС‚РєРё РїРѕ РёРЅС‚РµСЂРµСЃРЅС‹Рј С†РµРЅР°Рј.",
        "tagline": "РЎС‚РёР»СЊ РЅР° РєР°Р¶РґС‹Р№ РґРµРЅСЊ",
        "accent_color": "#f472b6",
        "accent_secondary": "#60a5fa",
        "logo_text": "РўРЎ",
        "category_focus_json": json.dumps(["sneakers", "apparel", "streetwear"], ensure_ascii=False),
        "feed_config_json": "",
        "sort_order": 3,
    },
    {
        "slug": "techno-halava",
        "name": "РўРµС…РЅРѕ РҐР°Р»СЏРІР°",
        "telegram_channel_url": "https://t.me/techno_halyava",
        "telegram_channel_id": "@techno_halyava",
        "niche": "РљРѕРјРїСЊСЋС‚РµСЂРЅС‹Рµ РєРѕРјРїР»РµРєС‚СѓСЋС‰РёРµ Рё РґРµРІР°Р№СЃС‹",
        "description": "РўРµС…РЅРёРєР°, РїРµСЂРёС„РµСЂРёСЏ, РєРѕРјРїР»РµРєС‚СѓСЋС‰РёРµ Рё РІС‹РіРѕРґРЅС‹Рµ РїСЂРµРґР»РѕР¶РµРЅРёСЏ РґР»СЏ РџРљ.",
        "tagline": "РўРµС…РЅРёРєР° Р±РµР· РїРµСЂРµРїР»Р°С‚С‹",
        "accent_color": "#ffb347",
        "accent_secondary": "#4d7cff",
        "logo_text": "РўРҐ",
        "category_focus_json": json.dumps(["laptops", "monitors", "keyboards", "mice", "components"], ensure_ascii=False),
        "feed_config_json": "",
        "sort_order": 4,
    },
]


def seed_defaults(db: Session) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        setting = db.get(AppSetting, key)
        if not setting:
            db.add(AppSetting(key=key, value=value))

    for package_data in DEFAULT_AD_PACKAGES:
        existing_package = db.scalar(select(AdPackage).where(AdPackage.code == package_data["code"]))
        if not existing_package:
            db.add(AdPackage(**package_data))
        else:
            for key, value in package_data.items():
                setattr(existing_package, key, value)

    project_rows: list[Project] = []
    for idx, project_data in enumerate(DEFAULT_PROJECTS):
        existing = db.scalar(select(Project).where(Project.slug == project_data["slug"]))
        if not existing:
            existing = Project(**project_data)
            db.add(existing)
        existing.sort_order = project_data["sort_order"]
        project_rows.append(existing)

    db.flush()

    for project in project_rows:
        for source in ["ozon", "wildberries", "yandex_market"]:
            template = db.scalar(
                select(ReferralTemplate).where(
                    ReferralTemplate.project_id == project.id,
                    ReferralTemplate.source == source,
                )
            )
            if not template:
                db.add(
                    ReferralTemplate(
                        project_id=project.id,
                        source=source,
                        name=f"{project.name} {source}",
                        template_url="{url}?utm_source={utm_source}&utm_medium={utm_medium}&utm_campaign={utm_campaign}",
                        utm_source="telegram",
                        utm_medium="affiliate",
                        utm_campaign=project.slug,
                    )
                )

        for source in ["ozon", "wildberries", "yandex_market"]:
            status = db.scalar(
                select(SyncStatus).where(
                    SyncStatus.project_id == project.id,
                    SyncStatus.source == source,
                )
            )
            if not status:
                db.add(SyncStatus(project_id=project.id, source=source, state="idle", total_items=0))

    db.commit()

