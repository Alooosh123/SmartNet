"""Wallet notification intake, payer identity approval and payment-intent APIs.

This module deliberately does not trust Android notification text as proof of payment.
Provider parsers must be shipped and reviewed individually before any automated fulfilment.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_current_admin, get_current_user
from config.settings import settings
from database import database, models
from services.subscription_agent import PLANS
from services.wallet_monitoring import (
    mask_wallet_identifier,
    parse_wallet_notification,
    wallet_fingerprint,
)

router = APIRouter(prefix="/api/v1/wallet-monitor", tags=["wallet-monitor"])


class ProviderCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]+$")
    display_name: str = Field(min_length=2, max_length=120)
    package_names: list[str] = Field(min_length=1, max_length=10)

    @field_validator("package_names")
    @classmethod
    def validate_packages(cls, values: list[str]) -> list[str]:
        cleaned = sorted({value.strip() for value in values if value.strip()})
        if not cleaned or any(len(value) > 200 or " " in value for value in cleaned):
            raise ValueError("Package names must be valid Android application IDs.")
        return cleaned


class DeviceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class ReceivingWalletCreate(BaseModel):
    provider_id: int = Field(gt=0)
    device_id: int = Field(gt=0)
    account_label: str = Field(min_length=2, max_length=120)
    account_identifier: str = Field(min_length=6, max_length=30)
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        result = value.strip().upper()
        if not result.isalpha():
            raise ValueError("Currency must be a three-letter code.")
        return result


class PayerWalletCreate(BaseModel):
    provider_id: int = Field(gt=0)
    wallet_identifier: str = Field(min_length=6, max_length=30)
    owner_name: str = Field(min_length=2, max_length=160)


class PaymentIntentCreate(BaseModel):
    payer_wallet_id: int = Field(gt=0)
    receiving_wallet_id: int = Field(gt=0)
    plan: Optional[str] = None


class DeviceHeartbeat(BaseModel):
    app_version: str = Field(min_length=1, max_length=40)
    notification_access_granted: bool


class DeviceNotification(BaseModel):
    event_uuid: str = Field(min_length=16, max_length=64)
    package_name: str = Field(min_length=3, max_length=200)
    title: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=4000)
    notification_posted_at: Optional[datetime] = None
    sent_at: datetime

    @field_validator("event_uuid")
    @classmethod
    def validate_event_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except ValueError as exc:
            raise ValueError("event_uuid must be a UUID.") from exc

    @field_validator("sent_at", "notification_posted_at")
    @classmethod
    def require_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamps must include a timezone.")
        return value


def _require_monitoring() -> None:
    if not settings.WALLET_MONITORING_ENABLED:
        raise HTTPException(status_code=503, detail="مراقبة المحافظ غير مفعلة حالياً.")


def _require_hmac_secret() -> None:
    if not settings.WALLET_IDENTITY_HMAC_SECRET or len(settings.WALLET_IDENTITY_HMAC_SECRET) < 32:
        raise HTTPException(status_code=503, detail="إعداد حماية هويات المحافظ غير مكتمل.")


async def _get_device_from_authorization(
    authorization: Optional[str],
    db: AsyncSession,
) -> models.WalletMonitorDevice:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="بيانات اعتماد الهاتف مطلوبة.")
    token = authorization[7:].strip()
    if len(token) < 32:
        raise HTTPException(status_code=401, detail="بيانات اعتماد الهاتف غير صالحة.")
    supplied_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(models.WalletMonitorDevice).where(
            models.WalletMonitorDevice.token_hash == supplied_hash,
            models.WalletMonitorDevice.status == "active",
        )
    )
    device = result.scalars().first()
    if not device or not hmac.compare_digest(device.token_hash, supplied_hash):
        raise HTTPException(status_code=401, detail="الهاتف غير مسجل أو تم إلغاؤه.")
    return device


async def _require_registration(registration_id: int, token: Optional[str], db: AsyncSession):
    result = await db.execute(
        select(models.RegistrationRequest).where(models.RegistrationRequest.id == registration_id)
    )
    registration = result.scalars().first()
    stored = registration.registration_token_hash if registration else None
    supplied = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    if not registration or not stored or not token or not hmac.compare_digest(stored, supplied):
        raise HTTPException(status_code=401, detail="رمز التسجيل غير صحيح.")
    if registration.processed:
        raise HTTPException(status_code=409, detail="تمت معالجة طلب التسجيل مسبقاً.")
    return registration


async def _create_payer_identity(
    db: AsyncSession,
    provider_id: int,
    wallet_identifier: str,
    owner_name: str,
    *,
    client_id: Optional[int] = None,
    registration_id: Optional[int] = None,
):
    _require_hmac_secret()
    provider_result = await db.execute(
        select(models.WalletProvider).where(
            models.WalletProvider.id == provider_id,
            models.WalletProvider.enabled.is_(True),
        )
    )
    provider = provider_result.scalars().first()
    if not provider:
        raise HTTPException(status_code=404, detail="مزود المحفظة غير متاح.")
    try:
        fingerprint = wallet_fingerprint(wallet_identifier)
        masked = mask_wallet_identifier(wallet_identifier)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    identity = models.PayerWalletIdentity(
        client_id=client_id,
        registration_id=registration_id,
        provider_id=provider.id,
        phone_fingerprint=fingerprint,
        masked_phone=masked,
        owner_name=owner_name.strip(),
        status="pending_approval",
    )
    db.add(identity)
    db.add(models.AuditLog(
        action="payer_wallet_identity_requested",
        performed_by=f"client:{client_id}" if client_id else f"registration:{registration_id}",
        details=f"Provider={provider.code}; payer wallet={masked}; approval required.",
    ))
    try:
        await db.commit()
        await db.refresh(identity)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="رقم المحفظة مسجل مسبقاً لدى هذا المزود.")
    return identity


@router.post("/admin/providers")
async def create_wallet_provider(
    payload: ProviderCreate,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    result = await db.execute(select(models.WalletProvider).where(models.WalletProvider.code == payload.code))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="رمز مزود المحفظة مستخدم مسبقاً.")
    provider = models.WalletProvider(
        code=payload.code,
        display_name=payload.display_name.strip(),
        package_allowlist=json.dumps(payload.package_names, ensure_ascii=False),
        parser_version=None,
        enabled=True,
        auto_verification_enabled=False,
    )
    db.add(provider)
    db.add(models.AuditLog(
        action="wallet_provider_created",
        performed_by=admin.username,
        details=f"Provider={payload.code}; packages={len(payload.package_names)}; auto verification disabled.",
    ))
    await db.commit()
    await db.refresh(provider)
    return {
        "id": provider.id,
        "code": provider.code,
        "display_name": provider.display_name,
        "package_names": payload.package_names,
        "auto_verification_enabled": False,
        "message": "تم تسجيل المزود. لا يوجد Parser معتمد له بعد، لذلك لن يعتمد أي إشعار تلقائياً.",
    }


@router.get("/admin/providers")
async def list_wallet_providers(
    db: AsyncSession = Depends(database.get_db),
    _admin=Depends(get_current_admin),
):
    result = await db.execute(select(models.WalletProvider).order_by(models.WalletProvider.id.asc()))
    providers = result.scalars().all()
    return [{
        "id": item.id,
        "code": item.code,
        "display_name": item.display_name,
        "package_names": json.loads(item.package_allowlist),
        "enabled": item.enabled,
        "parser_version": item.parser_version,
        "auto_verification_enabled": item.auto_verification_enabled,
    } for item in providers]


@router.post("/admin/devices")
async def create_wallet_monitor_device(
    payload: DeviceCreate,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    token = secrets.token_urlsafe(36)
    device_uuid = str(uuid.uuid4())
    device = models.WalletMonitorDevice(
        device_uuid=device_uuid,
        name=payload.name.strip(),
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        status="active",
        notification_access_granted=False,
    )
    db.add(device)
    db.add(models.AuditLog(
        action="wallet_monitor_device_created",
        performed_by=admin.username,
        details=f"Created dedicated wallet notification device {device_uuid}. Secret displayed once.",
    ))
    await db.commit()
    await db.refresh(device)
    return {
        "id": device.id,
        "device_uuid": device.device_uuid,
        "name": device.name,
        "device_token": token,
        "token_displayed_once": True,
        "message": "احفظ الرمز في تطبيق الهاتف عبر قناة آمنة. لن يظهر مرة أخرى.",
    }


@router.get("/admin/devices")
async def list_wallet_monitor_devices(
    db: AsyncSession = Depends(database.get_db),
    _admin=Depends(get_current_admin),
):
    result = await db.execute(select(models.WalletMonitorDevice).order_by(models.WalletMonitorDevice.id.desc()))
    return [{
        "id": item.id,
        "device_uuid": item.device_uuid,
        "name": item.name,
        "status": item.status,
        "app_version": item.app_version,
        "notification_access_granted": item.notification_access_granted,
        "last_seen_at": item.last_seen_at,
        "created_at": item.created_at,
    } for item in result.scalars().all()]


@router.post("/admin/devices/{device_id}/revoke")
async def revoke_wallet_monitor_device(
    device_id: int,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    device = await db.get(models.WalletMonitorDevice, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="الهاتف غير موجود.")
    device.status = "revoked"
    device.revoked_at = datetime.now(timezone.utc)
    device.token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    db.add(models.AuditLog(
        action="wallet_monitor_device_revoked",
        performed_by=admin.username,
        details=f"Revoked wallet monitor device {device.device_uuid}.",
    ))
    await db.commit()
    return {"ok": True, "status": "revoked"}


@router.post("/admin/receiving-wallets")
async def create_receiving_wallet(
    payload: ReceivingWalletCreate,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    _require_hmac_secret()
    provider = await db.get(models.WalletProvider, payload.provider_id)
    device = await db.get(models.WalletMonitorDevice, payload.device_id)
    if not provider or not provider.enabled:
        raise HTTPException(status_code=404, detail="مزود المحفظة غير متاح.")
    if not device or device.status != "active":
        raise HTTPException(status_code=404, detail="هاتف المراقبة غير نشط.")
    try:
        fingerprint = wallet_fingerprint(payload.account_identifier)
        masked = mask_wallet_identifier(payload.account_identifier)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    account = models.ReceivingWalletAccount(
        provider_id=provider.id,
        device_id=device.id,
        account_label=payload.account_label.strip(),
        account_fingerprint=fingerprint,
        masked_identifier=masked,
        currency=payload.currency,
        is_active=True,
    )
    db.add(account)
    db.add(models.AuditLog(
        action="receiving_wallet_account_created",
        performed_by=admin.username,
        details=f"Provider={provider.code}; receiving account={masked}; currency={payload.currency}.",
    ))
    try:
        await db.commit()
        await db.refresh(account)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="حساب الاستقبال مسجل مسبقاً.")
    return {
        "id": account.id,
        "provider_id": account.provider_id,
        "device_id": account.device_id,
        "account_label": account.account_label,
        "masked_identifier": account.masked_identifier,
        "currency": account.currency,
        "is_active": account.is_active,
    }


@router.post("/registrations/{registration_id}/payer-wallets")
async def add_registration_payer_wallet(
    registration_id: int,
    payload: PayerWalletCreate,
    x_registration_token: Optional[str] = Header(None, alias="X-Registration-Token"),
    db: AsyncSession = Depends(database.get_db),
):
    registration = await _require_registration(registration_id, x_registration_token, db)
    return await _create_payer_identity(
        db,
        payload.provider_id,
        payload.wallet_identifier,
        payload.owner_name,
        registration_id=registration.id,
    )


@router.post("/me/payer-wallets")
async def add_client_payer_wallet(
    payload: PayerWalletCreate,
    db: AsyncSession = Depends(database.get_db),
    current_user=Depends(get_current_user),
):
    if current_user.get("role") != "client":
        raise HTTPException(status_code=403, detail="هذه الخدمة مخصصة لأصحاب الشبكات.")
    return await _create_payer_identity(
        db,
        payload.provider_id,
        payload.wallet_identifier,
        payload.owner_name,
        client_id=current_user["id"],
    )


@router.post("/admin/payer-wallets/{identity_id}/approve")
async def approve_payer_wallet_identity(
    identity_id: int,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    identity = await db.get(models.PayerWalletIdentity, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="هوية المحفظة غير موجودة.")
    if identity.status == "revoked":
        raise HTTPException(status_code=409, detail="لا يمكن اعتماد هوية ملغاة؛ اطلب تسجيلاً جديداً.")
    identity.status = "active"
    identity.approved_by = admin.username
    identity.approved_at = datetime.now(timezone.utc)
    db.add(models.AuditLog(
        action="payer_wallet_identity_approved",
        performed_by=admin.username,
        details=f"Approved payer wallet identity #{identity.id} ({identity.masked_phone}).",
    ))
    await db.commit()
    return {"ok": True, "identity_id": identity.id, "status": identity.status}


@router.post("/admin/payer-wallets/{identity_id}/revoke")
async def revoke_payer_wallet_identity(
    identity_id: int,
    db: AsyncSession = Depends(database.get_db),
    admin=Depends(get_current_admin),
):
    identity = await db.get(models.PayerWalletIdentity, identity_id)
    if not identity:
        raise HTTPException(status_code=404, detail="هوية المحفظة غير موجودة.")
    identity.status = "revoked"
    identity.revoked_at = datetime.now(timezone.utc)
    db.add(models.AuditLog(
        action="payer_wallet_identity_revoked",
        performed_by=admin.username,
        details=f"Revoked payer wallet identity #{identity.id} ({identity.masked_phone}).",
    ))
    await db.commit()
    return {"ok": True, "identity_id": identity.id, "status": identity.status}


@router.post("/registrations/{registration_id}/payment-intents")
async def create_registration_payment_intent(
    registration_id: int,
    payload: PaymentIntentCreate,
    x_registration_token: Optional[str] = Header(None, alias="X-Registration-Token"),
    db: AsyncSession = Depends(database.get_db),
):
    registration = await _require_registration(registration_id, x_registration_token, db)
    return await _create_payment_intent(
        db,
        payer_wallet_id=payload.payer_wallet_id,
        receiving_wallet_id=payload.receiving_wallet_id,
        registration=registration,
        client=None,
        plan=registration.plan or "monthly",
    )


@router.post("/me/payment-intents")
async def create_renewal_payment_intent(
    payload: PaymentIntentCreate,
    db: AsyncSession = Depends(database.get_db),
    current_user=Depends(get_current_user),
):
    if current_user.get("role") != "client":
        raise HTTPException(status_code=403, detail="هذه الخدمة مخصصة لأصحاب الشبكات.")
    plan = payload.plan or current_user["obj"].plan or "monthly"
    return await _create_payment_intent(
        db,
        payer_wallet_id=payload.payer_wallet_id,
        receiving_wallet_id=payload.receiving_wallet_id,
        registration=None,
        client=current_user["obj"],
        plan=plan,
    )


async def _create_payment_intent(
    db: AsyncSession,
    *,
    payer_wallet_id: int,
    receiving_wallet_id: int,
    registration,
    client,
    plan: str,
):
    payer = await db.get(models.PayerWalletIdentity, payer_wallet_id)
    receiving = await db.get(models.ReceivingWalletAccount, receiving_wallet_id)
    if not payer or not receiving or not receiving.is_active:
        raise HTTPException(status_code=404, detail="هوية المرسل أو حساب الاستقبال غير متاح.")
    if payer.provider_id != receiving.provider_id:
        raise HTTPException(status_code=400, detail="يجب أن تكون محفظة المرسل والاستقبال من المزود نفسه.")
    if payer.status == "revoked":
        raise HTTPException(status_code=403, detail="هوية محفظة المرسل ملغاة.")
    if registration:
        if payer.registration_id != registration.id or payer.client_id is not None:
            raise HTTPException(status_code=403, detail="هوية المحفظة لا تتبع طلب التسجيل.")
        amount = Decimal(str(registration.price or 0)).quantize(Decimal("0.01"))
        currency = (registration.currency or "USD").upper()
        intent_type = "initial"
        client_id = None
        registration_id = registration.id
    else:
        if payer.client_id != client.id or payer.status != "active":
            raise HTTPException(status_code=403, detail="يجب اعتماد محفظة المرسل وربطها بحسابك أولاً.")
        if plan not in PLANS:
            raise HTTPException(status_code=400, detail="الباقة المطلوبة غير متاحة.")
        amount = Decimal(str(PLANS[plan]["price"])).quantize(Decimal("0.01"))
        currency = "USD"
        intent_type = "renewal"
        client_id = client.id
        registration_id = None
    if amount <= 0:
        raise HTTPException(status_code=400, detail="قيمة طلب الدفع غير صالحة.")
    intent = models.WalletPaymentIntent(
        client_id=client_id,
        registration_id=registration_id,
        payer_wallet_id=payer.id,
        receiving_wallet_id=receiving.id,
        intent_type=intent_type,
        plan=plan,
        amount=amount,
        currency=currency,
        reference_token=f"SN-{secrets.token_hex(10).upper()}",
        status="open",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(intent)
    db.add(models.AuditLog(
        action="wallet_payment_intent_created",
        performed_by=f"client:{client.id}" if client else f"registration:{registration.id}",
        details=f"Wallet intent created; type={intent_type}; plan={plan}; amount={amount} {currency}; receiving wallet={receiving.id}.",
    ))
    await db.commit()
    await db.refresh(intent)
    return {
        "intent_id": intent.id,
        "intent_type": intent.intent_type,
        "reference_token": intent.reference_token,
        "plan": intent.plan,
        "amount": str(intent.amount),
        "currency": intent.currency,
        "receiving_wallet": {
            "id": receiving.id,
            "label": receiving.account_label,
            "masked_identifier": receiving.masked_identifier,
            "currency": receiving.currency,
        },
        "expires_at": intent.expires_at,
        "status": intent.status,
        "automatic_activation": False,
        "message": "تم إنشاء طلب الدفع. سيبقى بانتظار تحقق المزود واعتماد أول ربط للمحفظة.",
    }


@router.post("/device/heartbeat")
async def wallet_device_heartbeat(
    payload: DeviceHeartbeat,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(database.get_db),
):
    _require_monitoring()
    device = await _get_device_from_authorization(authorization, db)
    device.app_version = payload.app_version
    device.notification_access_granted = payload.notification_access_granted
    device.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "ok": True,
        "device_uuid": device.device_uuid,
        "notification_access_granted": device.notification_access_granted,
        "server_time": datetime.now(timezone.utc),
    }


@router.post("/device/events")
async def receive_wallet_notification(
    payload: DeviceNotification,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(database.get_db),
):
    _require_monitoring()
    device = await _get_device_from_authorization(authorization, db)
    now = datetime.now(timezone.utc)
    sent_at = payload.sent_at.astimezone(timezone.utc)
    if abs((now - sent_at).total_seconds()) > settings.WALLET_DEVICE_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=400, detail="توقيت إرسال الحدث خارج النافذة المسموحة.")
    if not device.notification_access_granted:
        raise HTTPException(status_code=409, detail="يجب منح الهاتف صلاحية الوصول إلى الإشعارات أولاً.")
    if not payload.title and not payload.body:
        raise HTTPException(status_code=400, detail="الإشعار لا يحتوي على محتوى قابل للتحليل.")

    duplicate_result = await db.execute(
        select(models.WalletNotificationEvent).where(
            models.WalletNotificationEvent.device_id == device.id,
            models.WalletNotificationEvent.event_uuid == payload.event_uuid,
        )
    )
    duplicate = duplicate_result.scalars().first()
    if duplicate:
        device.last_seen_at = now
        await db.commit()
        return {"ok": True, "duplicate": True, "event_id": duplicate.id, "parse_status": duplicate.parse_status}

    payload_bytes = "\n".join((payload.package_name, payload.title, payload.body)).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    provider_result = await db.execute(select(models.WalletProvider).where(models.WalletProvider.enabled.is_(True)))
    providers = provider_result.scalars().all()
    provider = None
    for candidate in providers:
        try:
            packages = json.loads(candidate.package_allowlist)
        except (TypeError, json.JSONDecodeError):
            packages = []
        if payload.package_name in packages:
            provider = candidate
            break

    event = models.WalletNotificationEvent(
        device_id=device.id,
        provider_id=provider.id if provider else None,
        event_uuid=payload.event_uuid,
        package_name=payload.package_name,
        payload_sha256=payload_hash,
        parse_status="unknown_package" if not provider else "awaiting_provider_adapter",
        reason_code="package_not_allowlisted" if not provider else "provider_adapter_not_registered",
        notification_posted_at=payload.notification_posted_at,
    )
    if provider:
        try:
            parsed = parse_wallet_notification(provider.code, payload.title, payload.body)
        except Exception:
            parsed = None
            event.parse_status = "parse_error"
            event.reason_code = "provider_parser_error"
        if parsed:
            try:
                event.provider_transaction_id = (parsed.provider_transaction_id or "").strip() or None
                event.provider_reference = (parsed.provider_reference or "").strip() or None
                event.sender_fingerprint = wallet_fingerprint(parsed.sender_identifier)
                event.recipient_fingerprint = wallet_fingerprint(parsed.recipient_identifier)
                event.amount = Decimal(str(parsed.amount)).quantize(Decimal("0.01"))
                event.currency = parsed.currency.strip().upper()
                event.provider_status = parsed.provider_status.strip().lower()
                event.parse_status = "candidate_for_review"
                event.reason_code = "human_review_required"
                event.notification_posted_at = parsed.occurred_at or payload.notification_posted_at
            except (ValueError, RuntimeError, InvalidOperation, AttributeError):
                event.parse_status = "parse_error"
                event.reason_code = "invalid_parser_output"

    device.last_seen_at = now
    db.add(event)
    try:
        await db.flush()
        db.add(models.WalletPaymentReview(
            event_id=event.id,
            reason_code=event.reason_code or "manual_review_required",
            status="open",
        ))
        db.add(models.AuditLog(
            action="wallet_notification_received",
            performed_by=f"wallet-device:{device.device_uuid}",
            details=f"Event={event.event_uuid}; package={event.package_name}; parse_status={event.parse_status}; payload_sha256={payload_hash}.",
        ))
        await db.commit()
        await db.refresh(event)
    except IntegrityError:
        await db.rollback()
        existing_result = await db.execute(
            select(models.WalletNotificationEvent).where(
                models.WalletNotificationEvent.device_id == device.id,
                models.WalletNotificationEvent.event_uuid == payload.event_uuid,
            )
        )
        existing = existing_result.scalars().first()
        if existing:
            return {"ok": True, "duplicate": True, "event_id": existing.id, "parse_status": existing.parse_status}
        raise HTTPException(status_code=409, detail="تعذر تسجيل الحدث بسبب تعارض في البيانات.")

    return {
        "ok": True,
        "duplicate": False,
        "event_id": event.id,
        "parse_status": event.parse_status,
        "reason_code": event.reason_code,
        "automatic_activation": False,
    }


@router.get("/admin/events")
async def list_wallet_notification_events(
    limit: int = 100,
    db: AsyncSession = Depends(database.get_db),
    _admin=Depends(get_current_admin),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="الحد يجب أن يكون بين 1 و500.")
    result = await db.execute(
        select(models.WalletNotificationEvent)
        .order_by(models.WalletNotificationEvent.id.desc())
        .limit(limit)
    )
    return [{
        "id": item.id,
        "device_id": item.device_id,
        "provider_id": item.provider_id,
        "event_uuid": item.event_uuid,
        "package_name": item.package_name,
        "payload_sha256": item.payload_sha256,
        "parse_status": item.parse_status,
        "reason_code": item.reason_code,
        "amount": str(item.amount) if item.amount is not None else None,
        "currency": item.currency,
        "provider_status": item.provider_status,
        "provider_transaction_id": item.provider_transaction_id,
        "provider_reference": item.provider_reference,
        "received_at": item.received_at,
    } for item in result.scalars().all()]
