from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Product, ProductImage, Project, ReferralTemplate, SyncStatus
from app.services.dedup import build_dedup_key, is_duplicate
from app.services.marketplaces.collector import collect_marketplace_products
from app.services.marketplace_links import build_marketplace_links
from app.services.referrals import build_affiliate_url
from app.services.scoring import score_product


def _characteristics_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


def _item_characteristics(item) -> dict:
    value = item.characteristics if isinstance(item.characteristics, dict) else {}
    data = dict(value)
    data["marketplace_links"] = build_marketplace_links(
        {
            "source": item.source,
            "title": item.title,
            "brand": item.brand,
            "url": item.url,
            "characteristics": data,
        }
    )
    return data


def _update_existing_product(db: Session, product: Product, item, affiliate_url: str | None) -> Product:
    product.title = item.title
    product.brand = item.brand
    product.category = item.category
    product.price = item.price
    product.market_price = item.market_price
    product.discount_percent = item.discount_percent
    product.rating = item.rating
    product.reviews_count = item.reviews_count
    product.stock_count = item.stock_count
    product.url = item.url
    product.affiliate_url = affiliate_url or item.url
    product.description = item.description
    product.characteristics_json = _characteristics_json(_item_characteristics(item))
    product.score = score_product(item.__dict__).score
    product.updated_at = datetime.utcnow()
    db.query(ProductImage).filter(ProductImage.product_id == product.id).delete()
    for index, image_url in enumerate(item.images):
        db.add(ProductImage(product_id=product.id, url=image_url, is_primary=index == 0))
    return product


def upsert_product(db: Session, project: Project, item, referral_url: str | None = None) -> Product | None:
    affiliate_url = referral_url or item.url
    referral_template = db.scalar(
        select(ReferralTemplate).where(
            ReferralTemplate.project_id == project.id,
            ReferralTemplate.source == item.source,
            ReferralTemplate.is_active.is_(True),
        )
    )
    if referral_template and item.url:
        affiliate_url = build_affiliate_url(
            referral_template.template_url,
            item.url,
            item.source,
            {
                "utm_source": referral_template.utm_source,
                "utm_medium": referral_template.utm_medium,
                "utm_campaign": referral_template.utm_campaign,
            },
        )

    existing_exact = db.scalar(
        select(Product).where(
            Product.project_id == project.id,
            Product.source == item.source,
            Product.source_id == item.source_id,
        )
    )
    if existing_exact:
        return _update_existing_product(db, existing_exact, item, affiliate_url)

    existing_products = [
        {
            "title": product.title,
            "brand": product.brand,
            "category": product.category,
        }
        for product in db.scalars(select(Product).where(Product.project_id == project.id, Product.is_active.is_(True))).all()
    ]
    if is_duplicate(existing_products, item.title, item.brand, item.category):
        return None

    dedup_key = build_dedup_key(item.title, item.brand, item.category)
    scoring = score_product(item.__dict__)
    product = Product(
        project_id=project.id,
        source=item.source,
        source_id=item.source_id,
        title=item.title,
        brand=item.brand,
        category=item.category,
        price=item.price,
        market_price=item.market_price,
        discount_percent=item.discount_percent,
        rating=item.rating,
        reviews_count=item.reviews_count,
        stock_count=item.stock_count,
        url=item.url,
        affiliate_url=affiliate_url,
        description=item.description,
        characteristics_json=_characteristics_json(_item_characteristics(item)),
        dedup_key=dedup_key,
        score=scoring.score,
    )
    db.add(product)
    db.flush()
    for index, image_url in enumerate(item.images):
        db.add(ProductImage(product_id=product.id, url=image_url, is_primary=index == 0))
    return product


def import_products(db: Session, project: Project) -> dict[str, int]:
    imported = 0
    skipped = 0
    products = collect_marketplace_products(project)
    for item in products:
        try:
            product = upsert_product(db, project, item)
            if product:
                imported += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
    for source in {"ozon", "wildberries", "yandex_market"}:
        status = db.scalar(select(SyncStatus).where(SyncStatus.project_id == project.id, SyncStatus.source == source))
        if not status:
            status = SyncStatus(project_id=project.id, source=source, state="synced", total_items=imported)
            db.add(status)
        status.last_synced_at = datetime.utcnow()
        status.state = "synced"
        status.total_items = imported
        status.last_error = None
    db.commit()
    return {"imported": imported, "skipped": skipped}
