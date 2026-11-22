import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy.future import select

from config.settings import settings
from database import models

logger = logging.getLogger(__name__)

PLANS: Dict[str, Dict[str, Any]] = {
    "monthly": {
        "id": "monthly", "name": "شهري", "price": 20, "days": 30,
        "can_reboot_network": False, "can_disconnect_users": False,
        "can_print_cards": False, "chatbot_tier": "basic",
        "daily_chat_limit": 20,
        "features": ["شات بوت ذكي (20 رسالة يومياً)", "الدعم الفني", "متابعة حالة الاتصال والاستهلاك"],
    },
    "semi_annual": {
        "id": "semi_annual", "name": "نصف سنة", "price": 60, "days": 180,
        "can_reboot_network": False, "can_disconnect_users": True,
        "can_print_cards": True, "chatbot_tier": "advanced",
        "daily_chat_limit": 300,
        "features": ["شات بوت متقدم", "توليد حتى 100 كرت للدفعة", "فصل المستخدمين النشطين"],
    },
    "annual": {
        "id": "annual", "name": "سنوي", "price": 100, "days": 365,
        "can_reboot_network": True, "can_disconnect_users": True,
        "can_print_cards": True, "chatbot_tier": "unlimited_pro",
        "daily_chat_limit": None,
        "features": ["رسائل غير محدودة", "إعادة تشغيل الراوتر", "إدارة المستخدمين والكروت"],
    },
}


async def is_bot_enabled(db) -> bool:
    result = await db.execute(
        select(models.SystemSetting).where(models.SystemSetting.key == "subscription_bot_enabled")
    )
    setting = result.scalars().first()
    return setting.value.lower() == "true" if setting else True


async def set_bot_enabled(db, enabled: bool) -> bool:
    result = await db.execute(
        select(models.SystemSetting).where(models.SystemSetting.key == "subscription_bot_enabled")
    )
    setting = result.scalars().first()
    if setting is None:
        db.add(models.SystemSetting(key="subscription_bot_enabled", value=str(enabled).lower()))
    else:
        setting.value = str(enabled).lower()
    await db.commit()
    return enabled


async def process_pending_registrations(db, force_now: bool = False) -> int:
    """Send reminders only. Payment evidence never activates a subscription.

    Activation is intentionally a separate, authenticated administrator action
    after checking the payment provider or manually validating the remittance.
    """
    if not await is_bot_enabled(db):
        return 0

    result = await db.execute(
        select(models.RegistrationRequest)
        .where(models.RegistrationRequest.processed.is_(False))
        .order_by(models.RegistrationRequest.id.asc())
    )
    registrations = result.scalars().all()
    now = datetime.now(timezone.utc)
    changed = False

    for registration in registrations:
        created_at = registration.created_at or now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if not force_now and now - created_at < timedelta(seconds=settings.SUBSCRIPTION_AGENT_DELAY_SECONDS):
            continue

        if registration.paid:
            action = "bot_paid_review_notice"
            notice = (
                f"تم استلام إشعار دفع طلب الاشتراك رقم {registration.id}. "
                "الطلب بانتظار مراجعة وتأكيد الإدارة قبل تفعيل الحساب."
            )
        elif registration.receipt_image:
            action = "bot_receipt_review_notice"
            notice = (
                f"تم استلام صورة الحوالة لطلب الاشتراك رقم {registration.id}. "
                "الصورة ليست إثبات دفع آلياً؛ الطلب بانتظار التحقق اليدوي من الإدارة."
            )
        else:
            action = "bot_unpaid_notice"
            plan = PLANS.get(registration.plan or "monthly", PLANS["monthly"])
            notice = (
                f"طلب الاشتراك ({plan['name']}) بقيمة ${registration.price or plan['price']} "
                "ما زال بانتظار الدفع."
            )

        marker = f"registration #{registration.id}"
        previous = await db.execute(
            select(models.AuditLog)
            .where(
                models.AuditLog.action == action,
                models.AuditLog.details.contains(marker),
            )
            .limit(1)
        )
        if previous.scalars().first():
            continue

        db.add(models.ChatMessage(
            username=registration.username,
            sender="bot",
            message=notice,
        ))
        db.add(models.AuditLog(
            action=action,
            performed_by="subscription_agent",
            details=f"Sent status notice for {marker}",
        ))
        changed = True

    if changed:
        await db.commit()
    return 0


async def subscription_agent_loop(stop_event: asyncio.Event) -> None:
    from database.database import AsyncSessionLocal

    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                await process_pending_registrations(session)
        except Exception:
            logger.exception("Subscription notification cycle failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(5, settings.SUBSCRIPTION_AGENT_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            continue
