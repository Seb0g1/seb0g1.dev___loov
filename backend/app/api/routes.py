from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.models.entities import AdPackage, AdRequest, AppSetting, DraftPost, GenerationLog, ManualException, Product, ProductImage, Project, PublishedPost, PublishLog, ReferralTemplate, ScheduleItem, SyncStatus
from app.schemas.common import (
    AnalyticsResponse,
    AdInvoiceRequest,
    AdPackageRead,
    AdPackageUpdate,
    AdPublishRequest,
    AdRequestRead,
    AdRequestUpdate,
    DraftDecisionRequest,
    DraftUpdate,
    DraftRead,
    GenerateDraftRequest,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    PublishLogRead,
    GenerationLogRead,
    ProjectRead,
    ProjectUpdate,
    ReferralTemplateRead,
    ScheduleRequest,
    SyncStatusRead,
    SettingsItem,
    SettingsPatch,
)
from app.services.analytics import build_analytics
from app.services.advertising import (
    build_ad_packages_text,
    delete_expired_ad_posts,
    publish_ad_to_channels,
    send_payment_message_to_user,
    send_payment_offer,
    send_publication_link_to_user,
)
from app.services.dedup import build_dedup_key
from app.services.drafts import create_draft_from_product, product_to_payload, regenerate_draft
from app.services.importer import import_products
from app.services.publishing import publish_draft
from app.services.review_actions import process_draft_decision
from app.services.runtime_config import SECRET_KEYS, load_runtime_config, public_runtime_settings
from app.services.scoring import score_product
from app.services.telegram import TelegramPublisher, verify_message_exists
from app.services.seed import seed_defaults
from app.workers.scheduler import restart_scheduler


router = APIRouter()


def get_project_context(db: Session, project_id: int | None = None) -> Project | None:
    if project_id is None:
        return None
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def to_product_read(product: Product) -> ProductRead:
    payload = product_to_payload(product)
    payload.pop("id", None)
    return ProductRead(
        **payload,
        project_id=product.project_id,
        dedup_key=product.dedup_key,
        score=product.score,
        created_at=product.created_at,
        updated_at=product.updated_at,
        id=product.id,
    )


def to_ad_package_read(package: AdPackage) -> AdPackageRead:
    return AdPackageRead.model_validate(package)


def to_ad_request_read(request: AdRequest) -> AdRequestRead:
    return AdRequestRead.model_validate(request)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(project_id: int | None = None, db: Session = Depends(get_db)):
    return build_analytics(db, project_id)


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.sort_order.asc(), Project.id.asc())).all()


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.get("/products", response_model=list[ProductRead])
def list_products(project_id: int | None = None, db: Session = Depends(get_db), limit: int = 200, offset: int = 0, q: str | None = None):
    query = select(Product).order_by(Product.score.desc(), Product.created_at.desc()).offset(offset).limit(limit)
    if project_id is not None:
        query = query.where(Product.project_id == project_id)
    if q:
        like = f"%{q}%"
        query = query.where(Product.title.ilike(like))
    products = db.scalars(query).all()
    return [to_product_read(product) for product in products]


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(product_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    return to_product_read(product)


@router.post("/products/import")
def import_products_endpoint(project_id: int | None = None, db: Session = Depends(get_db)):
    project = get_project_context(db, project_id)
    if project is None:
        projects = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.sort_order.asc(), Project.id.asc())).all()
        imported = 0
        skipped = 0
        for item in projects:
            result = import_products(db, item)
            imported += result["imported"]
            skipped += result["skipped"]
        return {"imported": imported, "skipped": skipped}
    result = import_products(db, project)
    return result


@router.post("/products/{product_id}/exclude")
def exclude_product(product_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_excluded = True
    product.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/products/{product_id}/activate")
def activate_product(product_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_excluded = False
    product.is_active = True
    db.commit()
    return {"ok": True}


@router.post("/products/{product_id}/score")
def rescore_product(product_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    payload = product_to_payload(product)
    product.score = score_product(payload).score
    db.commit()
    return {"ok": True, "score": product.score}


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, payload: ProductUpdate, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    updates = payload.model_dump(exclude_unset=True)
    characteristics = updates.pop("characteristics", None)
    for key, value in updates.items():
        setattr(product, key, value)
    if characteristics is not None:
        product.characteristics_json = json.dumps(characteristics, ensure_ascii=False)
    product.dedup_key = build_dedup_key(product.title, product.brand, product.category)
    payload_product = product_to_payload(product)
    product.score = score_product(payload_product).score
    db.commit()
    db.refresh(product)
    return to_product_read(product)


@router.get("/drafts", response_model=list[DraftRead])
def list_drafts(project_id: int | None = None, db: Session = Depends(get_db), limit: int = 100, status: str | None = None):
    query = select(DraftPost).order_by(DraftPost.created_at.desc()).limit(limit)
    if project_id is not None:
        query = query.where(DraftPost.project_id == project_id)
    if status:
        query = query.where(DraftPost.status == status)
    return db.scalars(query).all()


@router.get("/drafts/{draft_id}", response_model=DraftRead)
def get_draft(draft_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/drafts/from-product/{product_id}", response_model=DraftRead)
async def create_draft(product_id: int, request: GenerateDraftRequest, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    draft = await create_draft_from_product(db, product, style=request.style)
    return draft


@router.post("/drafts/{draft_id}/regenerate", response_model=DraftRead)
async def regenerate(draft_id: int, request: GenerateDraftRequest, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    return await regenerate_draft(db, draft, regenerate_text=request.regenerate_text, regenerate_image=request.regenerate_image)


@router.patch("/drafts/{draft_id}", response_model=DraftRead)
def update_draft(draft_id: int, payload: DraftUpdate, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(draft, key, value)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/approve", response_model=DraftRead)
async def approve_draft(draft_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    await publish_draft(db, draft)
    db.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/decision")
async def decide_draft(draft_id: int, payload: DraftDecisionRequest, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    result = await process_draft_decision(db, draft_id, payload.action)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "Decision failed"))
    return result


@router.post("/drafts/{draft_id}/duplicate", response_model=DraftRead)
def duplicate_draft(draft_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    clone = DraftPost(
        project_id=draft.project_id,
        product_id=draft.product_id,
        title=f"{draft.title} (copy)",
        text=draft.text,
        style=draft.style,
        image_path=draft.image_path,
        status="draft",
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


@router.post("/drafts/{draft_id}/schedule", response_model=DraftRead)
def schedule_draft(draft_id: int, request: ScheduleRequest, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = "scheduled"
    draft.scheduled_for = request.run_at
    schedule = ScheduleItem(project_id=draft.project_id, draft_id=draft.id, run_at=request.run_at, status="pending")
    db.add(schedule)
    db.commit()
    db.refresh(draft)
    return draft


@router.post("/drafts/{draft_id}/publish")
async def publish_draft_endpoint(draft_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "published":
        raise HTTPException(status_code=409, detail="Draft already published")
    published = await publish_draft(db, draft)
    return {"ok": True, "published_id": published.id}


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    draft = db.get(DraftPost, draft_id)
    if not draft or (project_id is not None and draft.project_id != project_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    db.delete(draft)
    db.commit()
    return {"ok": True}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    items = db.scalars(select(AppSetting).order_by(AppSetting.key.asc())).all()
    rows = [{"key": item.key, "value": item.value} for item in items if item.key not in SECRET_KEYS]
    known = {item["key"] for item in rows}
    for item in public_runtime_settings(db):
        if item["key"] not in known:
            rows.append(item)
    return rows


@router.put("/settings")
def update_settings(payload: SettingsPatch, db: Session = Depends(get_db)):
    for key, value in payload.values.items():
        if key in SECRET_KEYS and value.strip() in {"", "[saved]"}:
            continue
        item = db.get(AppSetting, key)
        if not item:
            item = AppSetting(key=key, value=value)
            db.add(item)
        else:
            item.value = value
    db.commit()
    restart_scheduler()
    return {"ok": True}


@router.post("/settings/telegram/test-token")
async def test_telegram_token(db: Session = Depends(get_db)):
    runtime = load_runtime_config(db)
    if not runtime.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"https://api.telegram.org/bot{runtime.telegram_bot_token}/getMe")
    data = response.json()
    if not response.is_success or not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("description", "Telegram token test failed"))
    user = data.get("result", {})
    username = user.get("username") or ""
    if username:
        item = db.get(AppSetting, "telegram_bot_username")
        if not item:
            db.add(AppSetting(key="telegram_bot_username", value=username))
        else:
            item.value = username
        db.commit()
    return {"ok": True, "bot": user}


@router.post("/settings/telegram/test-admin")
async def test_telegram_admin(db: Session = Depends(get_db)):
    runtime = load_runtime_config(db)
    if not runtime.telegram_admin_id:
        raise HTTPException(status_code=400, detail="Telegram admin id is not configured")
    publisher = TelegramPublisher()
    result = await publisher.send_message(
        chat_id=str(runtime.telegram_admin_id),
        text="РўРµСЃС‚ Р±РѕС‚Р°: Р°РґРјРёРЅ-РїР°РЅРµР»СЊ РїРѕРґРєР»СЋС‡РµРЅР°, СѓРІРµРґРѕРјР»РµРЅРёСЏ СЂР°Р±РѕС‚Р°СЋС‚.",
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "Admin test failed")
    return {"ok": True, "message_id": result.message_id}


@router.post("/settings/telegram/test-channels")
async def test_telegram_channels(db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.sort_order.asc(), Project.id.asc())).all()
    publisher = TelegramPublisher()
    results = []
    for project in projects:
        if not project.telegram_channel_id:
            results.append({"project_id": project.id, "project": project.name, "ok": False, "error": "Channel id is empty"})
            continue
        result = await publisher.send_message(
            chat_id=project.telegram_channel_id,
            text=f"РўРµСЃС‚ Р±РѕС‚Р°: РєР°РЅР°Р» В«{project.name}В» РїРѕРґРєР»СЋС‡РµРЅ.",
        )
        results.append(
            {
                "project_id": project.id,
                "project": project.name,
                "channel_id": project.telegram_channel_id,
                "ok": result.ok,
                "message_id": result.message_id,
                "error": result.error,
            }
        )
    return {"ok": all(item["ok"] for item in results), "results": results}


@router.post("/settings/payments/test")
async def test_payment_settings(db: Session = Depends(get_db)):
    runtime = load_runtime_config(db)
    yookassa_ok = bool(runtime.yookassa_shop_id and runtime.yookassa_secret_key)
    cryptobot_ok = bool(runtime.cryptobot_api_token and runtime.cryptobot_asset)
    return {
        "ok": yookassa_ok or cryptobot_ok,
        "yookassa": {"ok": yookassa_ok, "shop_id": runtime.yookassa_shop_id},
        "cryptobot": {"ok": cryptobot_ok, "asset": runtime.cryptobot_asset},
    }


@router.get("/referrals", response_model=list[ReferralTemplateRead])
def list_referrals(project_id: int | None = None, db: Session = Depends(get_db)):
    query = select(ReferralTemplate).order_by(ReferralTemplate.source.asc())
    if project_id is not None:
        query = query.where(ReferralTemplate.project_id == project_id)
    return db.scalars(query).all()


@router.get("/published")
def published_posts(project_id: int | None = None, db: Session = Depends(get_db), limit: int = 50):
    query = select(PublishedPost).order_by(PublishedPost.published_at.desc()).limit(limit)
    if project_id is not None:
        query = query.where(PublishedPost.project_id == project_id)
    rows = db.scalars(query).all()
    return rows


@router.post("/published/{published_id}/verify")
async def verify_published(published_id: int, project_id: int | None = None, db: Session = Depends(get_db)):
    post = db.get(PublishedPost, published_id)
    if not post or (project_id is not None and post.project_id != project_id):
        raise HTTPException(status_code=404, detail="Published post not found")
    channel = post.telegram_chat_id
    if not channel:
        raise HTTPException(status_code=400, detail="Channel is not stored")
    exists = await verify_message_exists(channel, post.telegram_message_id or 0)
    post.checked_at = datetime.utcnow()
    post.is_verified = exists
    db.commit()
    return {"ok": True, "exists": exists}


@router.get("/logs/generation", response_model=list[GenerationLogRead])
def generation_logs(project_id: int | None = None, db: Session = Depends(get_db), limit: int = 100):
    query = select(GenerationLog).order_by(GenerationLog.created_at.desc()).limit(limit)
    if project_id is not None:
        query = query.where(GenerationLog.project_id == project_id)
    return db.scalars(query).all()


@router.get("/logs/publish", response_model=list[PublishLogRead])
def publish_logs(project_id: int | None = None, db: Session = Depends(get_db), limit: int = 100):
    query = select(PublishLog).order_by(PublishLog.created_at.desc()).limit(limit)
    if project_id is not None:
        query = query.where(PublishLog.project_id == project_id)
    return db.scalars(query).all()


@router.get("/sync-status", response_model=list[SyncStatusRead])
def sync_status(project_id: int | None = None, db: Session = Depends(get_db)):
    query = select(SyncStatus).order_by(SyncStatus.source.asc())
    if project_id is not None:
        query = query.where(SyncStatus.project_id == project_id)
    return db.scalars(query).all()


@router.get("/ads/packages", response_model=list[AdPackageRead])
def list_ad_packages(db: Session = Depends(get_db)):
    packages = db.scalars(select(AdPackage).order_by(AdPackage.sort_order.asc(), AdPackage.id.asc())).all()
    if not packages:
        seed_defaults(db)
        packages = db.scalars(select(AdPackage).order_by(AdPackage.sort_order.asc(), AdPackage.id.asc())).all()
    return packages


@router.patch("/ads/packages/{package_id}", response_model=AdPackageRead)
def update_ad_package(package_id: int, payload: AdPackageUpdate, db: Session = Depends(get_db)):
    package = db.get(AdPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(package, key, value)
    db.commit()
    db.refresh(package)
    return package


@router.get("/ads/requests", response_model=list[AdRequestRead])
def list_ad_requests(db: Session = Depends(get_db), limit: int = 100, status: str | None = None):
    query = select(AdRequest).order_by(AdRequest.created_at.desc()).limit(limit)
    if status:
        query = query.where(AdRequest.status == status)
    return db.scalars(query).all()


@router.get("/ads/requests/{request_id}", response_model=AdRequestRead)
def get_ad_request(request_id: int, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Ad request not found")
    return request


async def _set_ad_paid(db: Session, request: AdRequest) -> AdRequest:
    request.status = "in_work"
    request.paid_at = datetime.utcnow()
    request.in_work_at = datetime.utcnow()
    db.commit()
    db.refresh(request)
    publisher = TelegramPublisher()
    await publisher.send_message(chat_id=request.chat_id, text="РћРїР»Р°С‚Р° РїРѕР»СѓС‡РµРЅР°. РџРѕСЃС‚ РІ СЂР°Р±РѕС‚Рµ.")
    return request


@router.get("/ads/requests/{request_id}/media")
def ad_request_media(request_id: int, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request or not request.media_local_path:
        raise HTTPException(status_code=404, detail="Media not found")
    path = Path(request.media_local_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path)


@router.patch("/ads/requests/{request_id}", response_model=AdRequestRead)
def update_ad_request(request_id: int, payload: AdRequestUpdate, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Ad request not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(request, key, value)
    db.commit()
    db.refresh(request)
    return request


@router.post("/ads/requests/{request_id}/invoice", response_model=AdRequestRead)
async def create_ad_invoice(request_id: int, payload: AdInvoiceRequest, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Ad request not found")
    package = db.get(AdPackage, payload.package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    payment_result = await send_payment_offer(db, request, payload.provider, package)
    await send_payment_message_to_user(request, package, payment_result)
    request.admin_note = payload.note or request.admin_note
    db.commit()
    db.refresh(request)
    return request


@router.post("/ads/requests/{request_id}/mark-paid", response_model=AdRequestRead)
async def mark_ad_paid(request_id: int, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Ad request not found")
    return await _set_ad_paid(db, request)


@router.post("/ads/requests/{request_id}/publish", response_model=AdRequestRead)
async def publish_ad_request(request_id: int, payload: AdPublishRequest, db: Session = Depends(get_db)):
    request = db.get(AdRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Ad request not found")
    if payload.published_link:
        request.published_link = payload.published_link
        request.status = "published"
        request.published_at = datetime.utcnow()
        package = request.package if getattr(request, "package", None) else (db.get(AdPackage, request.package_id) if request.package_id else None)
        delete_hours = payload.auto_delete_hours or (package.delete_after_hours if package else 24)
        request.delete_at = datetime.utcnow() + timedelta(hours=delete_hours)
        db.commit()
        db.refresh(request)
        await send_publication_link_to_user(request)
        return request
    links = await publish_ad_to_channels(db, request)
    await send_publication_link_to_user(request)
    if not request.delete_at:
        package = request.package if getattr(request, "package", None) else (db.get(AdPackage, request.package_id) if request.package_id else None)
        request.delete_at = datetime.utcnow() + timedelta(hours=payload.auto_delete_hours or (package.delete_after_hours if package else 24))
        db.commit()
    return request


@router.post("/payments/yookassa/webhook")
async def yookassa_webhook(payload: dict, db: Session = Depends(get_db)):
    order_id = None
    data = payload.get("object") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        metadata = data.get("metadata") or {}
        order_id = metadata.get("order_id")
        order_id = order_id or data.get("metadata", {}).get("order_id")
    if not order_id and isinstance(payload, dict):
        order_id = payload.get("order_id")
    if not order_id:
        return {"ok": True, "ignored": True}
    request = db.get(AdRequest, int(order_id))
    if not request:
        return {"ok": True, "ignored": True}
    await _set_ad_paid(db, request)
    return {"ok": True}


@router.post("/payments/cryptobot/webhook")
async def cryptobot_webhook(payload: dict, db: Session = Depends(get_db)):
    order_id = None
    if isinstance(payload, dict):
        order_id = payload.get("order_id") or payload.get("payload")
        if isinstance(order_id, str) and order_id.startswith("order:"):
            order_id = order_id.split(":", 1)[1]
    if not order_id:
        return {"ok": True, "ignored": True}
    request = db.get(AdRequest, int(order_id))
    if not request:
        return {"ok": True, "ignored": True}
    await _set_ad_paid(db, request)
    return {"ok": True}


@router.post("/ads/requests/{request_id}/refresh")
async def refresh_ad_request(request_id: int, db: Session = Depends(get_db)):
    deleted = await delete_expired_ad_posts(db)
    return {"ok": True, "deleted": deleted}


@router.post("/products/{product_id}/exception")
def add_exception(product_id: int, reason: str, project_id: int | None = None, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product or (project_id is not None and product.project_id != project_id):
        raise HTTPException(status_code=404, detail="Product not found")
    db.add(ManualException(project_id=product.project_id, product_id=product_id, source=product.source, reason=reason))
    product.is_excluded = True
    product.is_active = False
    db.commit()
    return {"ok": True}


@router.post("/import-and-create-drafts")
async def import_and_create_drafts(style: str = "short", project_id: int | None = None, db: Session = Depends(get_db)):
    if project_id is None:
        projects = db.scalars(select(Project).where(Project.is_active.is_(True)).order_by(Project.sort_order.asc(), Project.id.asc())).all()
        import_total = 0
        drafted = 0
        for project in projects:
            result = import_products(db, project)
            import_total += result["imported"]
            candidate = db.scalar(
                select(Product)
                .where(
                    Product.project_id == project.id,
                    Product.is_excluded.is_(False),
                    Product.is_published.is_(False),
                )
                .order_by(Product.score.desc(), Product.created_at.desc())
                .limit(1)
            )
            if candidate:
                await create_draft_from_product(db, candidate, style=style)
                drafted += 1
        return {"imported": import_total, "drafted": drafted}
    project = get_project_context(db, project_id)
    import_result = import_products(db, project)
    drafted = 0
    products = db.scalars(
        select(Product)
        .where(Product.project_id == project.id, Product.is_excluded.is_(False), Product.is_published.is_(False))
        .order_by(Product.score.desc())
        .limit(5)
    ).all()
    for product in products:
        await create_draft_from_product(db, product, style=style)
        drafted += 1
    return {"imported": import_result, "drafted": drafted}

