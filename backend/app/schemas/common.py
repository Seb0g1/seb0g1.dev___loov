from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    project_id: int | None = None
    source: str
    source_id: str
    title: str
    brand: str | None = None
    category: str = "general"
    price: float
    market_price: float | None = None
    discount_percent: float | None = None
    rating: float | None = None
    reviews_count: int | None = None
    stock_count: int | None = None
    url: str | None = None
    affiliate_url: str | None = None
    description: str | None = None
    characteristics: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    is_excluded: bool = False
    is_published: bool = False
    notes: str | None = None


class ProductCreate(ProductBase):
    images: list[str] = Field(default_factory=list)


class ProductRead(ORMModel, ProductBase):
    id: int
    dedup_key: str
    score: float
    created_at: datetime
    updated_at: datetime
    images: list[str] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    project_id: int | None = None
    title: str | None = None
    brand: str | None = None
    category: str | None = None
    price: float | None = None
    market_price: float | None = None
    discount_percent: float | None = None
    rating: float | None = None
    reviews_count: int | None = None
    stock_count: int | None = None
    url: str | None = None
    affiliate_url: str | None = None
    description: str | None = None
    notes: str | None = None
    is_active: bool | None = None
    is_excluded: bool | None = None
    is_published: bool | None = None
    characteristics: dict[str, Any] | None = None


class DraftUpdate(BaseModel):
    project_id: int | None = None
    title: str | None = None
    text: str | None = None
    style: str | None = None
    image_path: str | None = None
    status: str | None = None
    scheduled_for: datetime | None = None
    approved_by: str | None = None


class DraftRead(ORMModel):
    id: int
    project_id: int | None = None
    product_id: int | None = None
    title: str
    text: str
    style: str
    image_path: str | None = None
    status: str
    scheduled_for: datetime | None = None
    published_at: datetime | None = None
    telegram_message_id: int | None = None
    telegram_chat_id: str | None = None
    created_at: datetime
    updated_at: datetime


class GenerateDraftRequest(BaseModel):
    style: str = "short"
    regenerate_text: bool = True
    regenerate_image: bool = True


class ScheduleRequest(BaseModel):
    run_at: datetime


class SettingsItem(BaseModel):
    key: str
    value: str


class SettingsPatch(BaseModel):
    values: dict[str, str]


class ReferralTemplateRead(ORMModel):
    id: int
    source: str
    name: str
    template_url: str
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    is_active: bool


class ProjectRead(ORMModel):
    id: int
    slug: str
    name: str
    telegram_channel_url: str | None = None
    telegram_channel_id: str | None = None
    niche: str
    description: str | None = None
    tagline: str | None = None
    accent_color: str
    accent_secondary: str
    logo_text: str
    category_focus_json: str | None = None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = None
    telegram_channel_url: str | None = None
    telegram_channel_id: str | None = None
    niche: str | None = None
    description: str | None = None
    tagline: str | None = None
    accent_color: str | None = None
    accent_secondary: str | None = None
    logo_text: str | None = None
    category_focus_json: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class GenerationLogRead(ORMModel):
    id: int
    project_id: int | None = None
    product_id: int | None = None
    draft_id: int | None = None
    kind: str
    provider: str
    prompt: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime


class PublishLogRead(ORMModel):
    id: int
    project_id: int | None = None
    draft_id: int | None = None
    product_id: int | None = None
    channel: str
    status: str
    telegram_message_id: int | None = None
    payload_json: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class SyncStatusRead(ORMModel):
    id: int
    project_id: int | None = None
    source: str
    last_synced_at: datetime | None = None
    last_error: str | None = None
    state: str
    total_items: int


class AnalyticsResponse(BaseModel):
    products_total: int
    products_active: int
    products_excluded: int
    drafts_total: int
    drafts_pending: int
    published_total: int
    average_score: float
    by_source: dict[str, int]
    by_status: dict[str, int]


class DraftDecisionRequest(BaseModel):
    action: str
    note: str | None = None


class AdPackageRead(ORMModel):
    id: int
    code: str
    name: str
    description: str | None = None
    amount: float
    duration_hours: int
    delete_after_hours: int
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class AdPackageUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    amount: float | None = None
    duration_hours: int | None = None
    delete_after_hours: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class AdRequestRead(ORMModel):
    id: int
    user_id: int
    chat_id: str
    username: str | None = None
    full_name: str | None = None
    text: str
    media_type: str
    media_file_id: str | None = None
    media_local_path: str | None = None
    status: str
    package_id: int | None = None
    package_name: str | None = None
    amount: float | None = None
    payment_provider: str | None = None
    payment_url: str | None = None
    payment_links_json: str | None = None
    external_payment_id: str | None = None
    admin_note: str | None = None
    published_link: str | None = None
    published_message_ids_json: str | None = None
    delete_at: datetime | None = None
    paid_at: datetime | None = None
    in_work_at: datetime | None = None
    published_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AdRequestUpdate(BaseModel):
    status: str | None = None
    package_id: int | None = None
    package_name: str | None = None
    amount: float | None = None
    payment_provider: str | None = None
    payment_url: str | None = None
    payment_links_json: str | None = None
    external_payment_id: str | None = None
    admin_note: str | None = None
    published_link: str | None = None


class AdInvoiceRequest(BaseModel):
    package_id: int
    provider: str
    note: str | None = None


class AdPublishRequest(BaseModel):
    published_link: str | None = None
    publish_to_channels: bool = True
    auto_delete_hours: int | None = None
