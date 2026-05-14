from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AdPackage, AppSetting, Project, ReferralTemplate, SyncStatus


DEFAULT_SETTINGS = {
    "default_style": "short",
    "auto_posting_enabled": "false",
    "theme": "dark-premium",
}

DEFAULT_AD_PACKAGES = [
    {
        "code": "all_channels_24h",
        "name": "Реклама во всех каналах 24 часа",
        "description": "Публикация рекламы во всех проектах сети на 24 часа.",
        "amount": 2500,
        "duration_hours": 24,
        "delete_after_hours": 24,
        "sort_order": 1,
    },
    {
        "code": "all_channels_48h",
        "name": "Реклама во всех каналах 48 часов",
        "description": "Публикация рекламы во всех проектах сети на 48 часов.",
        "amount": 3900,
        "duration_hours": 48,
        "delete_after_hours": 48,
        "sort_order": 2,
    },
    {
        "code": "sticky_story",
        "name": "История и закреп",
        "description": "Реклама с усиленным размещением и закрепом в каналах.",
        "amount": 4800,
        "duration_hours": 72,
        "delete_after_hours": 72,
        "sort_order": 3,
    },
]


DEFAULT_PROJECTS = [
    {
        "slug": "uyut-za-kopeiki",
        "name": "Уют за копейки",
        "telegram_channel_url": "https://t.me/yut_za_kopeiki",
        "telegram_channel_id": "@yut_za_kopeiki",
        "niche": "Всё для дома: уют и декор",
        "description": "Постельное белье, стильные лампы, органайзеры, посуда и эстетика Pinterest-дома.",
        "tagline": "Уютно, красиво и недорого",
        "accent_color": "#ffae42",
        "accent_secondary": "#4d7cff",
        "logo_text": "УЗК",
        "category_focus_json": json.dumps(["bedding", "lamps", "organizers", "tableware"], ensure_ascii=False),
        "sort_order": 1,
    },
    {
        "slug": "zheleznyi-vitamin",
        "name": "Железный Витамин",
        "telegram_channel_url": "https://t.me/zheleznyi_vitamin",
        "telegram_channel_id": "@zheleznyi_vitamin",
        "niche": "Спортпит и добавки",
        "description": "Протеин, витамины, креатин, омега-3 и всё, что берут каждый месяц.",
        "tagline": "Железо, витамины, энергия",
        "accent_color": "#7dd3fc",
        "accent_secondary": "#22c55e",
        "logo_text": "ЖВ",
        "category_focus_json": json.dumps(["protein", "vitamins", "creatine", "omega-3"], ensure_ascii=False),
        "sort_order": 2,
    },
    {
        "slug": "tochka-stilyev",
        "name": "Точка стиля",
        "telegram_channel_url": "https://t.me/tochka_stilyev",
        "telegram_channel_id": "@tochka_stilyev",
        "niche": "Кроссовки и брендовая одежда",
        "description": "Оригинальные кроссовки, одежда и прикольные шмотки по интересным ценам.",
        "tagline": "Стиль на каждый день",
        "accent_color": "#f472b6",
        "accent_secondary": "#60a5fa",
        "logo_text": "ТС",
        "category_focus_json": json.dumps(["sneakers", "apparel", "streetwear"], ensure_ascii=False),
        "sort_order": 3,
    },
    {
        "slug": "techno-halava",
        "name": "Техно Халява",
        "telegram_channel_url": "https://t.me/techno_halyava",
        "telegram_channel_id": "@techno_halyava",
        "niche": "Компьютерные комплектующие и девайсы",
        "description": "Техника, периферия, комплектующие и выгодные предложения для ПК.",
        "tagline": "Техника без переплаты",
        "accent_color": "#ffb347",
        "accent_secondary": "#4d7cff",
        "logo_text": "ТХ",
        "category_focus_json": json.dumps(["laptops", "monitors", "keyboards", "mice", "components"], ensure_ascii=False),
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
