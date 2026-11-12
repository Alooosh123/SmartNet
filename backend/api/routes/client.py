import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import database, models, schemas
from api.dependencies import get_current_user
from services.pdf_service import pdf_service
from services.mikrotik_service import mikrotik_service
from services.subscription_agent import PLANS

router = APIRouter(prefix="/client", tags=["client"])


def parse_print_cards_command(message: str):
    """Parse manager chat commands such as: اريد منك طباعة 100 كرت صلاحية يوم واحد."""
    normalized = message.translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
    if not re.search(r'\b(?:طباعة|اطبع|توليد)\b', normalized) or not re.search(r'(?:كرت|كروت|بطاقة|بطاقات)', normalized):
        return None

    count_match = re.search(r'(\d{1,4})\s*(?:كرت|كروت|بطاقة|بطاقات)', normalized)
    if not count_match:
        return None

    count = int(count_match.group(1))
    if count < 1 or count > 1000:
        raise HTTPException(status_code=400, detail='عدد الكروت يجب أن يكون بين 1 و 1000')

    if re.search(r'(?:يوم|يومًا|يوم واحد)', normalized):
        profile = '1 Day'
    elif re.search(r'(?:أسبوع|اسبوع|أسبوعًا)', normalized):
        profile = '1 Week'
    elif re.search(r'(?:شهر|شهري)', normalized):
        profile = '1 Month'
    else:
        profile = '1 Day'

    return {'count': count, 'profile': profile}


async def create_print_batch(command: dict, current_user, db: AsyncSession):
    """Create the same card batch and PDF used by the cards page."""
    cards = mikrotik_service.generate_cards(command['count'], command['profile'], 6)
    batch = models.CardBatch(
        profile=command['profile'],
        count=command['count'],
        owner_username=current_user.get('username'),
    )
    db.add(batch)
    await db.flush()

    batch.pdf_path = pdf_service.generate_cards_pdf(
        batch.id,
        cards,
        hide_password=False,
        profile=command['profile'],
    )

    for card_data in cards:
        db.add(models.Card(
            batch_id=batch.id,
            username=card_data['username'],
            password=card_data['password'],
        ))

    db.add(models.AuditLog(
        action='chat_generate_cards',
        performed_by=current_user.get('username', 'admin'),
        details=f"Generated {command['count']} cards from chat for profile {command['profile']} (batch #{batch.id})",
    ))
    await db.commit()
    await db.refresh(batch)
    return batch

@router.post('/chat')
async def post_chat_message(
    payload: dict,
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    # Non-admin users can only send messages under their own username
    if current_user.get("role") != "admin":
        username = current_user.get("username")
    else:
        username = payload.get('username') or current_user.get("username")

    raw_message = payload.get('message', '')
    if not isinstance(raw_message, str):
        raise HTTPException(status_code=422, detail='حقل الرسالة يجب أن يكون نصاً')
    message = raw_message.strip()
    if not message:
        raise HTTPException(status_code=400, detail='الرسالة لا يمكن أن تكون فارغة')
    if len(message) > 1500:
        raise HTTPException(status_code=400, detail='الحد الأقصى لطول الرسالة هو 1500 حرفاً')

    msg = models.ChatMessage(username=username, sender='client', message=message)
    db.add(msg)
    await db.flush()

    role = current_user.get("role")
    client_obj = current_user.get("obj")
    plan = getattr(client_obj, "plan", "monthly") or "monthly" if role != "admin" else "admin"
    plan_info = PLANS.get(plan, PLANS["monthly"])
    daily_limit = plan_info.get("daily_chat_limit") if role != "admin" else None

    # Check daily message quota
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    count_res = await db.execute(
        select(func.count(models.ChatMessage.id)).where(
            models.ChatMessage.username == username,
            models.ChatMessage.sender == "client",
            models.ChatMessage.created_at >= today_start,
        )
    )
    # Total sent today before current message
    sent_today_before = (count_res.scalar() or 0) - 1
    if sent_today_before < 0:
        sent_today_before = 0

    if daily_limit is not None and sent_today_before >= daily_limit:
        reply_text = (
            f"⚠️ لقد استهلكت رصيدك اليومي المخصص لرسائل الشات بوت "
            f"({sent_today_before}/{daily_limit} رسالة اليوم) في باقة ({plan_info['name']}).\n\n"
            "🔄 يتم تجديد الرصيد تلقائياً كل يوم عند منتصف الليل 🕛، أو يمكنك الترقية إلى باقة أعلى:\n"
            "• باقة نصف سنة: 300 رسالة يومياً ($60)\n"
            "• الباقة السنوية: رسائل غير محدودة ♾️ ($100)"
        )
        bot = models.ChatMessage(username=username, sender='bot', message=reply_text)
        db.add(bot)
        await db.commit()
        await db.refresh(bot)
        return {
            'reply': reply_text,
            'bot_message_id': bot.id,
            'model': 'smartnet-quota-exceeded',
            'daily_limit_reached': True,
            'daily_limit': daily_limit,
            'used_today': sent_today_before,
            'remaining_today': 0,
            'unlimited': False,
        }

    can_reboot = (role == "admin") or getattr(client_obj, "can_reboot_network", False) or (plan == "annual")

    normalized_msg = message.lower()
    is_reboot_cmd = bool(
        re.search(r'(?:اعادة تشغيل|إعادة تشغيل|اعمل ريبوت|سو ريبوت|ريبوت|اعيد تشغيل|ريستارت|اعمل ريستارت)', normalized_msg)
        and re.search(r'(?:شبكة|الشبكة|راوتر|الراوتر|مايكروتك|سيرفر|نت)', normalized_msg)
    )

    automation = None
    raw_command = parse_print_cards_command(message)

    if is_reboot_cmd:
        if can_reboot:
            reply_text = (
                "إعادة تشغيل الراوتر تؤثر على جميع المشتركين، لذلك لا أنفذها من رسالة محادثة. "
                "استخدم زر «إعادة تشغيل الشبكة» في صفحة حسابك، واقرأ رسالة التأكيد قبل المتابعة."
            )
            result = {"model": "smartnet-safe-action-guidance"}
        else:
            reply_text = (
                "صلاحية إعادة تشغيل الراوتر غير متاحة في باقتك الحالية. "
                "يمكنك طلب تنفيذ العملية من إدارة الشبكة."
            )
            result = {"model": "smartnet-permission-denied"}
    elif raw_command:
        if role == "admin" or plan in ["semi_annual", "annual"]:
            reply_text = (
                "لإنشاء الكروت ومراجعة العدد والمدة قبل التنفيذ، افتح صفحة «كروت الهوت سبوت» "
                "واستخدم نموذج إصدار دفعة جديدة. لن أنشئ حسابات على الراوتر بمجرد رسالة نصية."
            )
            result = {"model": "smartnet-safe-card-guidance"}
        else:
            reply_text = (
                "توليد الكروت متاح للباقة النصف سنوية والسنوية أو مدير النظام. "
                "يمكنك التواصل مع الإدارة للترقية."
            )
            result = {"model": "smartnet-card-restricted"}
    else:
        from services.chat_service import generate_reply
        result = await generate_reply(username, message, plan=plan)
        reply_text = result.get('text', 'تم استلام الرسالة')

    bot = models.ChatMessage(username=username, sender='bot', message=reply_text)
    db.add(bot)
    await db.commit()
    await db.refresh(bot)

    used_total = sent_today_before + 1
    remaining_today = max(0, daily_limit - used_total) if daily_limit is not None else None
    response = {
        'reply': reply_text,
        'bot_message_id': bot.id,
        'model': result.get('model'),
        'daily_limit': daily_limit,
        'used_today': used_total,
        'remaining_today': remaining_today,
        'unlimited': (daily_limit is None),
    }
    if automation:
        response.update(automation)
    return response


@router.get('/chat/quota', response_model=schemas.ChatQuotaResponse)
async def get_chat_quota(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db),
):
    """Return daily chat quota, messages used today, and remaining messages."""
    role = current_user.get("role")
    username = current_user.get("username")
    client_obj = current_user.get("obj")
    plan = getattr(client_obj, "plan", "monthly") or "monthly" if role != "admin" else "admin"
    plan_info = PLANS.get(plan, PLANS["monthly"])
    daily_limit = plan_info.get("daily_chat_limit") if role != "admin" else None

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    count_res = await db.execute(
        select(func.count(models.ChatMessage.id)).where(
            models.ChatMessage.username == username,
            models.ChatMessage.sender == "client",
            models.ChatMessage.created_at >= today_start,
        )
    )
    used_today = count_res.scalar() or 0
    remaining = max(0, daily_limit - used_today) if daily_limit is not None else None

    return schemas.ChatQuotaResponse(
        username=username,
        plan=plan,
        plan_name="مدير النظام" if role == "admin" else plan_info["name"],
        daily_limit=daily_limit,
        used_today=used_today,
        remaining_today=remaining,
        unlimited=(daily_limit is None),
    )


@router.get('/chat')
async def get_chat_messages(
    username: str,
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user)
):
    # Security: Non-admin users can only view their own chat messages (prevents IDOR)
    if current_user.get("role") != "admin" and current_user.get("username") != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="لا يمكنك الوصول إلى محادثات مستخدم آخر"
        )

    result = await db.execute(
        select(models.ChatMessage)
        .where(models.ChatMessage.username == username)
        .order_by(models.ChatMessage.id.asc())
    )
    msgs = result.scalars().all()
    return msgs

