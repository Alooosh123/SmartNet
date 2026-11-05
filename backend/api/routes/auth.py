from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import models, schemas, database
from services.auth_service import auth_service
from config.settings import settings
from database.schemas import RegistrationCreate
from api.dependencies import get_current_admin, get_current_user
from services.subscription_agent import PLANS, is_bot_enabled, set_bot_enabled, process_pending_registrations

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(database.get_db)
):
    username = form_data.username.strip()
    password = form_data.password

    # 1. Check Admin database table
    result = await db.execute(select(models.Admin).where(models.Admin.username == username))
    admin = result.scalars().first()
    if admin and auth_service.verify_password(password, admin.hashed_password):
        if not admin.is_active:
            raise HTTPException(status_code=403, detail="هذا الحساب معطل")
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": admin.username, "role": "admin"},
            expires_delta=access_token_expires,
        )
        db.add(models.AuditLog(action="login", performed_by=admin.username, details="Admin logged in via DB"))
        await db.commit()
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": "admin",
            "username": admin.username,
            "plan": "admin",
            "can_reboot_network": True,
        }

    # 2. Check fallback environment admin credentials
    if username == settings.DASHBOARD_USERNAME and password == settings.DASHBOARD_PASSWORD:
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": username, "role": "admin"},
            expires_delta=access_token_expires,
        )
        db.add(models.AuditLog(action="login", performed_by=username, details="Admin logged in via env credentials"))
        await db.commit()
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": "admin",
            "username": username,
            "plan": "admin",
            "can_reboot_network": True,
        }

    # 3. Check Client database table
    result = await db.execute(select(models.Client).where(models.Client.username == username))
    client = result.scalars().first()
    if client and auth_service.verify_password(password, client.hashed_password):
        if not client.is_active:
            raise HTTPException(status_code=403, detail="تم تعطيل هذا الحساب من قبل الإدارة")
        
        now = datetime.now(timezone.utc)
        exp = client.subscription_expires
        if exp:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                raise HTTPException(status_code=403, detail="انتهت فترة اشتراكك، يرجى التواصل مع الإدارة للتجديد")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = auth_service.create_access_token(
            data={"sub": client.username, "role": "client"},
            expires_delta=access_token_expires,
        )
        db.add(models.AuditLog(action="login", performed_by=client.username, details="Client logged in"))
        await db.commit()
        
        client_plan = client.plan or "monthly"
        can_reboot = bool(client.can_reboot_network or client_plan == "annual")
        can_cards = bool(client_plan in ["annual", "semi_annual"])
        can_users = bool(client_plan in ["annual", "semi_annual"])
        is_unlimited = bool(client_plan == "annual")
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": "client",
            "username": client.username,
            "plan": client_plan,
            "can_reboot_network": can_reboot,
            "can_manage_cards": can_cards,
            "can_manage_users": can_users,
            "is_unlimited": is_unlimited,
            "subscription_expires": client.subscription_expires.isoformat() if client.subscription_expires else None,
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="اسم المستخدم أو كلمة المرور غير صحيحة",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.get("/me", response_model=schemas.UserProfileResponse)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db),
):
    """Retrieve logged in user profile, plan, and active permissions."""
    role = current_user.get("role")
    username = current_user.get("username")
    if role == "admin":
        return schemas.UserProfileResponse(
            username=username,
            role="admin",
            plan="admin",
            can_reboot_network=True,
            can_manage_cards=True,
            can_manage_users=True,
            is_unlimited=True,
            is_active=True,
        )
    
    result = await db.execute(select(models.Client).where(models.Client.username == username))
    client = result.scalars().first()
    if not client:
        return schemas.UserProfileResponse(
            username=username,
            role=role or "client",
            plan="monthly",
            can_reboot_network=False,
            can_manage_cards=False,
            can_manage_users=False,
            is_unlimited=False,
            is_active=True,
        )
    
    client_plan = client.plan or "monthly"
    return schemas.UserProfileResponse(
        username=client.username,
        role="client",
        plan=client_plan,
        can_reboot_network=bool(client.can_reboot_network or client_plan == "annual"),
        can_manage_cards=bool(client_plan in ["annual", "semi_annual"]),
        can_manage_users=bool(client_plan in ["annual", "semi_annual"]),
        is_unlimited=bool(client_plan == "annual"),
        subscription_expires=client.subscription_expires.isoformat() if client.subscription_expires else None,
        is_active=client.is_active,
    )


@router.post("/setup")
async def setup_initial_admin(admin_in: schemas.AdminCreate, db: AsyncSession = Depends(database.get_db)):
    result = await db.execute(select(models.Admin).limit(1))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Admin already exists. Setup complete.")
    
    hashed_password = auth_service.get_password_hash(admin_in.password)
    new_admin = models.Admin(username=admin_in.username.strip(), hashed_password=hashed_password)
    db.add(new_admin)
    db.add(models.AuditLog(action="setup", performed_by=admin_in.username, details="Initial admin created"))
    await db.commit()
    return {"msg": "Admin created successfully."}


@router.post('/register')
async def register_user(payload: RegistrationCreate, db: AsyncSession = Depends(database.get_db)):
    """Save a registration request (pending) with chosen plan and return a payment URL."""
    username = payload.username.strip()
    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="اسم المستخدم يجب أن يكون 3 أحرف على الأقل")
    if not payload.password or len(payload.password) < 4:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 4 أحرف على الأقل")

    # check existing admin
    result = await db.execute(select(models.Admin).where(models.Admin.username == username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="اسم المستخدم مستخدم بالفعل")

    # check existing client
    result_client = await db.execute(select(models.Client).where(models.Client.username == username))
    if result_client.scalars().first():
        raise HTTPException(status_code=400, detail="اسم المستخدم مسجل بالفعل كعميل")

    # check existing pending registration
    result2 = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.username == username))
    if result2.scalars().first():
        raise HTTPException(status_code=400, detail="يوجد طلب تسجيل معلق مسبقاً بهذا الاسم")

    plan_key = (payload.plan or "monthly").lower()
    if plan_key not in PLANS:
        plan_key = "monthly"
    plan_info = PLANS[plan_key]

    hashed = auth_service.get_password_hash(payload.password)
    reg = models.RegistrationRequest(
        username=username,
        hashed_password=hashed,
        plan=plan_key,
        price=plan_info["price"]
    )
    db.add(reg)
    await db.flush()

    invoice_id = f"inv-{reg.id}-{username}"
    payment_url = None
    if settings.PAYMENT_CHECKOUT_URL:
        payment_url = settings.PAYMENT_CHECKOUT_URL.format(
            invoice_id=invoice_id,
            registration_id=reg.id,
            username=username,
        )
    elif settings.PAYMENT_DEMO_MODE:
        payment_url = f"{settings.APP_PUBLIC_URL.rstrip('/')}/payment/{reg.id}"

    reg.payment_ref = invoice_id
    db.add(models.AuditLog(
        action="register",
        performed_by=username,
        details=f"Registration request created #{reg.id} for plan {plan_info['name']} (${plan_info['price']})"
    ))
    await db.commit()
    await db.refresh(reg)

    return {
        "payment_required": bool(payment_url),
        "payment_url": payment_url,
        "registration_id": reg.id,
        "plan": plan_key,
        "price": plan_info["price"],
        "plan_name": plan_info["name"],
        "message": (
            f"تم إنشاء طلب الاشتراك في باقة ({plan_info['name']} - ${plan_info['price']}). يرجى إتمام الدفع للمصادقة وتفعيل الحساب."
            if payment_url else
            "تم إنشاء الطلب، بانتظار إعداد بوابة الدفع من المالك."
        )
    }


@router.get('/registrations', response_model=list[schemas.RegistrationResponse])
async def list_registrations(db: AsyncSession = Depends(database.get_db), current_admin = Depends(get_current_admin)):
    result = await db.execute(select(models.RegistrationRequest).order_by(models.RegistrationRequest.id.desc()))
    registrations = result.scalars().all()
    response = []
    for reg in registrations:
        payment_message = None
        message_result = await db.execute(
            select(models.ChatMessage)
            .where(
                models.ChatMessage.username == reg.username,
                models.ChatMessage.sender == "bot",
            )
            .order_by(models.ChatMessage.id.desc())
            .limit(1)
        )
        latest_message = message_result.scalars().first()
        if latest_message:
            payment_message = latest_message.message
        response.append({
            "id": reg.id,
            "username": reg.username,
            "plan": reg.plan or "monthly",
            "price": reg.price or 20,
            "paid": reg.paid,
            "payment_ref": reg.payment_ref,
            "receipt_image": reg.receipt_image,
            "processed": reg.processed,
            "payment_message": payment_message,
            "created_at": reg.created_at,
        })
    return response


@router.post('/registrations/{reg_id}/approve')
async def approve_registration(
    reg_id: int,
    days: Optional[int] = None,
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    """Approve a registration, create a client account with plan permissions and expiry."""
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    if reg.processed:
        raise HTTPException(status_code=400, detail="تمت معالجة هذا الطلب مسبقاً")
    if not reg.paid:
        raise HTTPException(status_code=400, detail="لا يمكن تفعيل المشترك قبل تأكيد الدفع")

    plan_key = reg.plan or "monthly"
    plan_info = PLANS.get(plan_key, PLANS["monthly"])
    actual_days = days if (days and days > 0) else plan_info["days"]

    if actual_days < 1 or actual_days > 3650:
        raise HTTPException(status_code=400, detail="عدد الأيام يجب أن يكون بين 1 و 3650")

    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=actual_days)

    existing_client = await db.execute(select(models.Client).where(models.Client.username == reg.username))
    client = existing_client.scalars().first()
    if not client:
        client = models.Client(
            username=reg.username,
            hashed_password=reg.hashed_password,
            plan=plan_key,
            can_reboot_network=plan_info["can_reboot_network"],
            subscription_expires=expires,
            is_active=True
        )
        db.add(client)
    else:
        client.plan = plan_key
        client.can_reboot_network = plan_info["can_reboot_network"]
        client.subscription_expires = expires
        client.is_active = True

    reg.processed = True
    db.add(models.AuditLog(
        action="approve_registration",
        performed_by=getattr(current_admin, 'username', 'admin'),
        details=f"Approved registration #{reg_id} for {reg.username} (Plan: {plan_info['name']}, {actual_days} days)"
    ))
    await db.commit()
    await db.refresh(client)
    return {
        "ok": True,
        "client_id": client.id,
        "username": client.username,
        "plan": client.plan,
        "can_reboot_network": client.can_reboot_network,
        "subscription_expires": client.subscription_expires
    }


@router.post('/registrations/{reg_id}/demo-pay')
async def demo_pay_registration(reg_id: int, db: AsyncSession = Depends(database.get_db)):
    """Complete a local demo payment; disabled automatically in production mode."""
    if not settings.PAYMENT_DEMO_MODE:
        raise HTTPException(status_code=404, detail="الدفع التجريبي غير متاح")

    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    if reg.processed:
        raise HTTPException(status_code=400, detail="تم تفعيل هذا الطلب مسبقاً")

    reg.paid = True
    reg.payment_ref = f"demo-{reg.id}"
    db.add(models.AuditLog(
        action="demo_payment_confirmed",
        performed_by="demo-payment",
        details=f"Demo payment confirmed for registration #{reg.id}; plan={reg.plan}",
    ))
    await db.commit()

    bot_active = await is_bot_enabled(db)
    if bot_active:
        await process_pending_registrations(db, force_now=True)
        await db.refresh(reg)

    if reg.processed:
        return {
            "ok": True,
            "paid": True,
            "processed": True,
            "message": "تم تأكيد الدفع وتفعيل حسابك تلقائياً بواسطة بوت المصادقة الذكي! يمكنك تسجيل الدخول الآن مباشرة.",
        }

    return {
        "ok": True,
        "paid": True,
        "processed": False,
        "message": "تم تأكيد الدفع التجريبي، والطلب بانتظار إتمام المصادقة أو موافقة مدير الشبكة.",
    }


@router.post('/registrations/{reg_id}/confirm')
async def confirm_payment(
    reg_id: int,
    days: int = 30,
    payment_ref: Optional[str] = None,
    secret: Optional[str] = Query(None),
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    db: AsyncSession = Depends(database.get_db),
):
    """Secure payment confirmation webhook.
    Requires PAYMENT_WEBHOOK_SECRET to prevent unauthorized free account activation.
    """
    provided_secret = secret or x_webhook_secret
    if not provided_secret or provided_secret != settings.PAYMENT_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="رمز أمان بوابة الدفع غير صحيح أو غير مصرح به"
        )

    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="عدد الأيام يجب أن يكون بين 1 و 3650")

    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    if reg.processed:
        return {"ok": False, "detail": "تمت معالجته مسبقاً"}

    reg.paid = True
    if payment_ref:
        reg.payment_ref = payment_ref
    db.add(models.AuditLog(action="webhook_payment_confirmed", performed_by="payment_gateway", details=f"Payment confirmed for registration #{reg_id}, awaiting admin approval, ref={payment_ref}"))
    await db.commit()
    return {
        "ok": True,
        "username": reg.username,
        "paid": True,
        "processed": False,
        "message": "تم تأكيد الدفع، والطلب بانتظار موافقة مدير الشبكة."
    }


@router.get('/registrations/{reg_id}/status')
async def registration_status(reg_id: int, db: AsyncSession = Depends(database.get_db)):
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    message_result = await db.execute(
        select(models.ChatMessage)
        .where(
            models.ChatMessage.username == reg.username,
            models.ChatMessage.sender == "bot",
        )
        .order_by(models.ChatMessage.id.desc())
        .limit(1)
    )
    latest_message = message_result.scalars().first()
    plan_key = reg.plan or "monthly"
    plan_info = PLANS.get(plan_key, PLANS["monthly"])
    return {
        "id": reg.id,
        "username": reg.username,
        "plan": plan_key,
        "price": reg.price or plan_info["price"],
        "plan_name": plan_info["name"],
        "paid": reg.paid,
        "processed": reg.processed,
        "payment_ref": reg.payment_ref,
        "receipt_image": reg.receipt_image,
        "payment_message": latest_message.message if latest_message else None,
    }


@router.post('/registrations/{reg_id}/receipt')
async def upload_registration_receipt(
    reg_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(database.get_db)
):
    """Upload remittance / bank transfer voucher receipt image."""
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")

    receipts_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "receipt.jpg").suffix or ".jpg"
    unique_filename = f"receipt_{reg.id}_{uuid.uuid4().hex[:8]}{ext}"
    target_path = receipts_dir / unique_filename

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="حجم الصورة كبير جداً (الحد الأقصى 10 ميجابايت)")

    with open(target_path, "wb") as f:
        f.write(contents)

    rel_url = f"/uploads/receipts/{unique_filename}"
    reg.receipt_image = rel_url

    db.add(models.AuditLog(
        action="receipt_uploaded",
        performed_by=reg.username,
        details=f"Remittance receipt uploaded for registration #{reg.id} ({unique_filename})"
    ))
    await db.commit()

    # Trigger automatic smart authentication bot to verify receipt and activate account
    bot_active = await is_bot_enabled(db)
    if bot_active:
        await process_pending_registrations(db, force_now=True)
        await db.refresh(reg)

    return {
        "ok": True,
        "receipt_url": rel_url,
        "processed": reg.processed,
        "paid": reg.paid,
        "message": "تم استلام سند التحويل بنجاح وفحصه واعتماد اشتراكك بواسطة بوت المصادقة الذكي! يمكنك تسجيل الدخول الآن مباشرة." if reg.processed else "تم رفع صورة الحوالة بنجاح، بانتظار استكمال التدقيق والمصادقة."
    }


@router.get('/clients', response_model=list[schemas.ClientResponse])
async def list_clients(db: AsyncSession = Depends(database.get_db), current_admin = Depends(get_current_admin)):
    result = await db.execute(select(models.Client).order_by(models.Client.id.desc()))
    return result.scalars().all()


@router.post('/clients/{client_id}/extend')
async def extend_client_subscription(
    client_id: int,
    days: int = 30,
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="عدد الأيام يجب أن يكون بين 1 و 3650")

    result = await db.execute(select(models.Client).where(models.Client.id == client_id))
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail='العميل غير موجود')

    now = datetime.now(timezone.utc)
    current = client.subscription_expires
    if current:
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        if current < now:
            current = now
    else:
        current = now

    new_exp = current + timedelta(days=days)
    client.subscription_expires = new_exp
    client.is_active = True
    db.add(models.AuditLog(action="extend_subscription", performed_by=getattr(current_admin, 'username', 'admin'), details=f"Extended client #{client_id} by {days} days"))
    await db.commit()
    await db.refresh(client)
    return {"ok": True, "client_id": client.id, "subscription_expires": client.subscription_expires}


@router.post('/clients/{client_id}/deactivate')
async def deactivate_client(
    client_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    result = await db.execute(select(models.Client).where(models.Client.id == client_id))
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail='العميل غير موجود')

    client.is_active = False
    db.add(models.AuditLog(action="deactivate_client", performed_by=getattr(current_admin, 'username', 'admin'), details=f"Deactivated client #{client_id} ({client.username})"))
    await db.commit()
    await db.refresh(client)
    return {"ok": True, "client_id": client.id, "is_active": client.is_active}


@router.get('/plans', response_model=list[schemas.PlanInfo])
async def get_subscription_plans():
    """Return available subscription plans with prices and permissions."""
    return list(PLANS.values())


@router.get('/owner/notifications', response_model=schemas.OwnerNotificationResponse)
async def get_owner_notifications(
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    """Fetch notifications for pending and unpaid registration requests for the owner."""
    result = await db.execute(select(models.RegistrationRequest).order_by(models.RegistrationRequest.id.desc()))
    registrations = result.scalars().all()
    pending = [r for r in registrations if not r.processed]
    paid_pending = [r for r in pending if r.paid]
    unpaid = [r for r in pending if not r.paid]

    recent = []
    for reg in pending[:10]:
        recent.append(schemas.RegistrationResponse(
            id=reg.id,
            username=reg.username,
            plan=reg.plan or "monthly",
            price=reg.price or 20,
            paid=reg.paid,
            payment_ref=reg.payment_ref,
            processed=reg.processed,
            payment_message=None,
            created_at=reg.created_at,
        ))

    return {
        "pending_count": len(pending),
        "unpaid_count": len(unpaid),
        "paid_pending_count": len(paid_pending),
        "recent_requests": recent,
    }


@router.get('/bot/status', response_model=schemas.BotStatusResponse)
async def get_bot_status(
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    """Get the current operational status of the subscription authentication bot."""
    enabled = await is_bot_enabled(db)
    count_res = await db.execute(
        select(models.AuditLog).where(models.AuditLog.action.in_(["bot_auth_approved", "subscription_agent_approved"]))
    )
    total_approved = len(count_res.scalars().all())

    return {
        "enabled": enabled,
        "name": "بوت المصادقة الذكي SmartNet",
        "last_run": datetime.now(timezone.utc).isoformat(),
        "total_auto_approved": total_approved,
        "mode": "فحص وتفعيل فوري للطلبات المسددة" if enabled else "إيقاف مؤقت",
    }


@router.post('/bot/toggle')
async def toggle_bot(
    enabled: bool = Query(...),
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    """Enable or disable the automatic authentication bot."""
    new_status = await set_bot_enabled(db, enabled)
    db.add(models.AuditLog(
        action="bot_toggle",
        performed_by=getattr(current_admin, 'username', 'admin'),
        details=f"Bot status set to {new_status}"
    ))
    await db.commit()
    return {"ok": True, "enabled": new_status}


@router.post('/bot/trigger')
async def trigger_bot(
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin)
):
    """Trigger the authentication bot immediately on all pending paid requests."""
    approved_count = await process_pending_registrations(db, force_now=True)
    return {
        "ok": True,
        "approved_count": approved_count,
        "message": f"قام بوت المصادقة بفحص الطلبات والمصادقة على {approved_count} طلب مسدد بنجاح!"
    }

