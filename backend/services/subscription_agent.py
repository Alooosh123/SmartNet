import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from sqlalchemy.future import select

from config.settings import settings
from database import models

logger = logging.getLogger(__name__)

PLANS: Dict[str, Dict[str, Any]] = {
    "monthly": {
        "id": "monthly",
        "name": "شهري",
        "price": 20,
        "days": 30,
        "can_reboot_network": False,
        "can_disconnect_users": False,
        "can_print_cards": False,
        "chatbot_tier": "basic",
        "daily_chat_limit": 20,
        "features": [
            "شات بوت ذكي مفعل (20 رسالة يومياً)",
            "استعلامات الشات بوت الأساسية والدعم الفني",
            "فحص حالة الاتصال ومعدل الاستهلاك",
            "تجديد الحساب والدعم الإرشادي",
        ]
    },
    "semi_annual": {
        "id": "semi_annual",
        "name": "نصف سنة",
        "price": 60,
        "days": 180,
        "can_reboot_network": False,
        "can_disconnect_users": True,
        "can_print_cards": True,
        "chatbot_tier": "advanced",
        "daily_chat_limit": 300,
        "features": [
            "شات بوت ذكي متقدم (300 رسالة يومياً)",
            "توليد وطباعة حتى 100 كرت عبر الدردشة",
            "صلاحية فصل المستخدمين والجلسات النشطة",
            "تشخيص متقدم لأعطال وبطء الشبكة",
            "أولوية في الدعم الفني",
        ]
    },
    "annual": {
        "id": "annual",
        "name": "سنوي",
        "price": 100,
        "days": 365,
        "can_reboot_network": True,
        "can_disconnect_users": True,
        "can_print_cards": True,
        "chatbot_tier": "unlimited_pro",
        "daily_chat_limit": None,
        "features": [
            "شات بوت ذكاء اصطناعي VIP (رسائل غير محدودة ♾️)",
            "صلاحية إعادة تشغيل شبكة الراوتر (Reboot) مباشرة",
            "تنفيذ أوامر الراوتر الفورية عبر الدردشة",
            "إدارة وفصل المستخدمين والتحكم بالجلسات",
            "توليد وطباعة الكروت بدون أي قيود",
            "مراقبة شاملة لأداء السيرفر وحركة البيانات",
        ]
    }
}


async def is_bot_enabled(db) -> bool:
    """Check if the subscription authentication bot is active."""
    res = await db.execute(select(models.SystemSetting).where(models.SystemSetting.key == "subscription_bot_enabled"))
    setting = res.scalars().first()
    if setting:
        return setting.value.lower() == "true"
    return True  # default enabled


async def set_bot_enabled(db, enabled: bool) -> bool:
    res = await db.execute(select(models.SystemSetting).where(models.SystemSetting.key == "subscription_bot_enabled"))
    setting = res.scalars().first()
    if not setting:
        setting = models.SystemSetting(key="subscription_bot_enabled", value=str(enabled).lower())
        db.add(setting)
    else:
        setting.value = str(enabled).lower()
    await db.commit()
    return enabled


async def process_pending_registrations(db, force_now: bool = False) -> int:
    """Verify and authenticate pending registrations automatically based on selected plan."""
    bot_active = await is_bot_enabled(db)
    if not bot_active and not force_now:
        return 0

    result = await db.execute(
        select(models.RegistrationRequest)
        .where(models.RegistrationRequest.processed.is_(False))
        .order_by(models.RegistrationRequest.id.asc())
    )
    registrations = result.scalars().all()
    now = datetime.now(timezone.utc)
    approved_count = 0
    changed = False

    for registration in registrations:
        created_at = registration.created_at or now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        # In standard background loop, respect grace period unless forced
        if not force_now and (now - created_at < timedelta(seconds=settings.SUBSCRIPTION_AGENT_DELAY_SECONDS)):
            continue

        plan_key = registration.plan or "monthly"
        plan_info = PLANS.get(plan_key, PLANS["monthly"])

        has_receipt = bool(getattr(registration, "receipt_image", None))
        if registration.paid or has_receipt:
            is_via_receipt = not registration.paid and has_receipt
            if is_via_receipt:
                registration.paid = True
                registration.payment_ref = f"receipt-{registration.id}"

            existing = await db.execute(
                select(models.Client).where(models.Client.username == registration.username)
            )
            client = existing.scalars().first()
            if not client:
                client = models.Client(
                    username=registration.username,
                    hashed_password=registration.hashed_password,
                    plan=plan_key,
                    can_reboot_network=plan_info["can_reboot_network"],
                    is_active=True,
                    subscription_expires=now + timedelta(days=plan_info["days"]),
                )
                db.add(client)
            else:
                client.plan = plan_key
                client.can_reboot_network = plan_info["can_reboot_network"]
                client.is_active = True
                client.subscription_expires = now + timedelta(days=plan_info["days"])

            registration.processed = True
            approved_count += 1

            # Welcome message in Chat
            approval_method = "بفحص صورة الحوالة وتأكيد السداد وتفعيل اشتراكك بنجاح" if is_via_receipt else "بتفعيل اشتراكك بنجاح"
            reboot_status = "مفعلة ✅ (تحكم كامل بالشبكة)" if plan_info['can_reboot_network'] else "غير مفعلة (متاحة في الباقة السنوية)"
            cards_status = "مفعلة بالكامل (كافة الفئات وطباعة غير محدودة) 💎" if plan_key == "annual" else ("متاحة حتى 100 كرت ⚡" if plan_key == "semi_annual" else "غير مفعلة")

            limit_desc = 'غير محدودة ♾️' if plan_info.get('daily_chat_limit') is None else f"{plan_info['daily_chat_limit']} رسالة يومياً"
            db.add(models.ChatMessage(
                username=registration.username,
                sender="bot",
                message=(
                    f"🎉 أهلاً بك {registration.username}! قام بوت المصادقة الذكي {approval_method} "
                    f"ضمن باقة ({plan_info['name']} - ${plan_info['price']}) بصلاحية {plan_info['days']} يوماً.\n\n"
                    f"• صلاحية إدارة وطباعة الكروت: {cards_status}\n"
                    f"• صلاحية إعادة تشغيل الراوتر: {reboot_status}\n"
                    f"• حصة الرسائل الذكية: {limit_desc}.\n\n"
                    f"نتمنى لك تجربة ممتعة وسلسة مع SmartNet!"
                ),
            ))

            audit_action = "bot_receipt_approved" if is_via_receipt else "bot_auth_approved"
            audit_details = (
                f"Smart Auth Bot verified remittance voucher and approved registration #{registration.id} ({registration.username}) for plan {plan_info['name']}"
                if is_via_receipt else
                f"Smart Auth Bot approved paid registration #{registration.id} ({registration.username}) for plan {plan_info['name']} (${plan_info['price']}, {plan_info['days']} days)"
            )

            db.add(models.AuditLog(
                action=audit_action,
                performed_by="auth_bot",
                details=audit_details,
            ))
            changed = True
            continue

        # For unpaid after grace period: send notice once
        notice_marker = f"registration #{registration.id}"
        notice_result = await db.execute(
            select(models.AuditLog).where(
                models.AuditLog.action == "bot_unpaid_notice",
                models.AuditLog.details.contains(notice_marker),
            ).limit(1)
        )
        if notice_result.scalars().first():
            continue

        db.add(models.ChatMessage(
            username=registration.username,
            sender="bot",
            message=(
                f"تنبيه من بوت المصادقة: طلب الاشتراك ({plan_info['name']}) بقيمة ${plan_info['price']} بانتظار الدفع. "
                "يرجى إتمام السداد لتفعيل حسابك وصلاحياتك تلقائياً."
            ),
        ))
        db.add(models.AuditLog(
            action="bot_unpaid_notice",
            performed_by="auth_bot",
            details=f"Sent unpaid notice for registration #{registration.id} ({registration.username})",
        ))
        changed = True

    if changed:
        await db.commit()

    return approved_count


async def subscription_agent_loop(stop_event):
    """Continuous background loop for the authentication bot."""
    from database.database import AsyncSessionLocal

    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                await process_pending_registrations(session)
        except Exception:
            logger.exception("Subscription agent cycle failed")
        try:
            await asyncio_wait(stop_event, settings.SUBSCRIPTION_AGENT_INTERVAL_SECONDS)
        except Exception:
            break


async def asyncio_wait(stop_event, seconds):
    import asyncio
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
