from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

import httpx

from app.services.runtime_config import load_runtime_config


@dataclass
class PaymentLinkResult:
    ok: bool
    payment_id: str | None
    payment_url: str | None
    error: str | None = None


async def create_payment_link(provider: str, amount: float, description: str, order_id: int) -> PaymentLinkResult:
    settings = load_runtime_config()
    provider = provider.lower().strip()
    if provider == "yookassa":
        if not settings.yookassa_shop_id or not settings.yookassa_secret_key:
            return PaymentLinkResult(False, None, None, "YooKassa is not configured")
        payload = {
            "amount": {"value": f"{Decimal(str(amount)):.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": settings.yookassa_return_url},
            "description": description,
            "metadata": {"order_id": str(order_id)},
        }
        auth = base64.b64encode(f"{settings.yookassa_shop_id}:{settings.yookassa_secret_key}".encode()).decode()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://api.yookassa.ru/v3/payments",
                headers={
                    "Authorization": f"Basic {auth}",
                    "Idempotence-Key": str(uuid4()),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return PaymentLinkResult(True, data.get("id"), data.get("confirmation", {}).get("confirmation_url"))

    if provider == "cryptobot":
        if not settings.cryptobot_api_token:
            return PaymentLinkResult(False, None, None, "CryptoBot is not configured")
        payload = {
            "asset": settings.cryptobot_asset,
            "amount": f"{Decimal(str(amount)):.2f}",
            "description": description,
            "payload": f"order:{order_id}",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                "https://pay.crypt.bot/api/createInvoice",
                headers={"Crypto-Pay-API-Token": settings.cryptobot_api_token},
                json=payload,
            )
            response.raise_for_status()
            data = response.json().get("result", {})
            return PaymentLinkResult(True, str(data.get("invoice_id")), data.get("pay_url"))

    return PaymentLinkResult(False, None, None, f"Unsupported payment provider: {provider}")
