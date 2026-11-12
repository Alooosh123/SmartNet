from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
import uuid
import hashlib
import hmac
import secrets
from io import BytesIO
from PIL import Image
from fastapi import APIRouter, Depends, HTTPException, status, Header, Query, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import models, schemas, database
from services.auth_service import auth_service
from config.settings import settings
from database.schemas import RegistrationCreate
from api.dependencies import get_current_admin, get_current_user
from services.subscription_agent import PLANS, is_bot_enabled, set_bot_enabled, process_pending_registrations

def _registration_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _require_registration_token(registration: models.RegistrationRequest, token: Optional[str]) -> None:
    stored = getattr(registration, "registration_token_hash", None)
    if not token or not stored or not hmac.compare_digest(_registration_token_hash(token), stored):
        raise HTTPException(status_code=401, detail="رمز الوصول إلى طلب التسجيل غير صحيح")


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

    # Bootstrap credentials are only used to create the initial DB admin at startup.
    # They are deliberately not a parallel authentication path.
    # 2. Check Client database table
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


@router.post("/change-password")
async def change_password(
    payload: schemas.PasswordChange,
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    """Change the authenticated administrator or subscriber's password."""
    user_obj = current_user.get("obj")
    if user_obj is None:
        raise HTTPException(status_code=401, detail="الحساب غير متاح")

    if not auth_service.verify_password(payload.current_password, user_obj.hashed_password):
        raise HTTPException(status_code=400, detail="كلمة المرور الحالية غير صحيحة")

    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="اختر كلمة مرور جديدة مختلفة")

    try:
        user_obj.hashed_password = auth_service.get_password_hash(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.add(models.AuditLog(
        action="change_password",
        performed_by=current_user.get("username", "user"),
        details=f"Password changed for {current_user.get('role', 'user')} account",
    ))
    await db.commit()
    return {"ok": True, "message": "تم تغيير كلمة المرور بنجاح. سجّل الدخول مجدداً."}


@router.post("/setup")
async def setup_initial_admin(admin_in: schemas.AdminCreate, db: AsyncSession = Depends(database.get_db)):
    # Production administrator bootstrap is performed from protected environment variables.
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=404, detail="المسار غير متاح في بيئة الإنتاج")
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
    if not payload.password or len(payload.password) < 10:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 10 أحرف على الأقل")

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
        raise HTTPException(status_code=400, detail="الباقة المحددة غير متاحة")
    plan_info = PLANS[plan_key]

    hashed = auth_service.get_password_hash(payload.password)
    registration_token = secrets.token_urlsafe(32)
    reg = models.RegistrationRequest(
        username=username,
        hashed_password=hashed,
        plan=plan_key,
        price=plan_info["price"],
        registration_token_hash=_registration_token_hash(registration_token),
    )
    db.add(reg)
    await db.flush()

    invoice_id = f"smartnet-{reg.id}-{uuid.uuid4().hex}"
    payment_url = None
    if settings.PAYMENT_PROVIDER_MODE == "gateway" and settings.PAYMENT_CHECKOUT_URL:
        payment_url = settings.PAYMENT_CHECKOUT_URL.format(
            invoice_id=invoice_id,
            registration_id=reg.id,
            username=username,
        )
    # In local demo mode the customer uses the authenticated demo-pay endpoint.
    # No fake checkout URL is returned because the repository does not bundle a
    # simulated payment web page or a real payment provider.

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
        "payment_demo_available": bool(settings.PAYMENT_DEMO_MODE and settings.ENVIRONMENT.lower() != "production"),
        "registration_id": reg.id,
        "registration_token": registration_token,
        "plan": plan_key,
        "price": plan_info["price"],
        "plan_name": plan_info["name"],
        "message": (
            f"تم إنشاء طلب الاشتراك في باقة ({plan_info['name']} - ${plan_info['price']}). أكمل الدفع عبر البوابة المحددة."
            if payment_url else
            ("تم إنشاء الطلب. يمكنك إكمال الدفع التجريبي في بيئة التطوير." if settings.PAYMENT_DEMO_MODE and settings.ENVIRONMENT.lower() != "production" else "تم إنشاء الطلب. حوّل المبلغ عبر قناة الدفع المتفق عليها ثم ارفع صورة الحوالة لمراجعتها من الإدارة.")
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
            "receipt_image": f"/auth/registrations/{reg.id}/receipt" if reg.receipt_image else None,
            "processed": reg.processed,
            "payment_message": payment_message,
            "created_at": reg.created_at,
        })
    return response


@router.post('/registrations/{reg_id}/verify-manual')
async def verify_manual_payment(
    reg_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_admin = Depends(get_current_admin),
):
    """Record an administrator's manual confirmation of money received.

    This is an auditable decision made only after checking the actual bank/mobile
    wallet account outside SmartNet. It marks payment as verified but does not
    activate the client; activation remains a separate approval action.
    """
    result = await db.execute(
        select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id)
    )
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    if reg.processed:
        raise HTTPException(status_code=409, detail="تم اعتماد هذا الطلب مسبقاً")
    if reg.paid:
        return {"ok": True, "paid": True, "processed": False, "detail": "الدفع مسجل كمؤكد مسبقاً"}

    reg.paid = True
    if not reg.payment_ref or reg.payment_ref.startswith("smartnet-"):
        reg.payment_ref = f"manual-{reg.id}-{uuid.uuid4().hex}"
    db.add(models.AuditLog(
        action="manual_payment_verified",
        performed_by=getattr(current_admin, "username", "admin"),
        details=f"Administrator manually verified money receipt for registration #{reg.id}; client activation remains pending",
    ))
    await db.commit()
    return {
        "ok": True,
        "paid": True,
        "processed": False,
        "message": "تم تسجيل تأكيد وصول المبلغ. يجب اعتماد الاشتراك بصورة منفصلة لتفعيل الحساب.",
    }


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
async def demo_pay_registration(
    reg_id: int,
    x_registration_token: Optional[str] = Header(None, alias="X-Registration-Token"),
    db: AsyncSession = Depends(database.get_db),
):
    """Local-only demonstration payment; never activates an account by itself."""
    if not settings.PAYMENT_DEMO_MODE or settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=404, detail="الدفع التجريبي غير متاح")

    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    _require_registration_token(reg, x_registration_token)
    if reg.processed:
        raise HTTPException(status_code=409, detail="تمت معالجة هذا الطلب مسبقاً")

    reg.paid = True
    reg.payment_ref = f"demo-{reg.id}"
    db.add(models.AuditLog(
        action="demo_payment_confirmed",
        performed_by=f"registration:{reg.id}",
        details=f"Demo payment marked for registration #{reg.id}; admin approval still required",
    ))
    await db.commit()
    return {
        "ok": True,
        "paid": True,
        "processed": False,
        "message": "تم تسجيل الدفع التجريبي. الحساب لا يتفعّل إلا بعد موافقة المدير.",
    }


@router.post('/registrations/{reg_id}/confirm')
async def confirm_payment(
    reg_id: int,
    payment_ref: str,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    db: AsyncSession = Depends(database.get_db),
):
    """Accept a trusted provider callback and mark payment for administrator review.

    The shared secret authenticates the callback channel. A production provider
    adapter must additionally validate its signature, event ID, amount and currency
    before calling this endpoint.
    """
    if settings.PAYMENT_PROVIDER_MODE != "gateway":
        raise HTTPException(status_code=404, detail="إشعارات بوابة الدفع الخارجية غير مفعلة في وضع الدفع اليدوي")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, settings.PAYMENT_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="رمز أمان بوابة الدفع غير صحيح أو غير مصرح به")
    if not payment_ref or not payment_ref.strip() or payment_ref.strip().lower().startswith("demo-"):
        raise HTTPException(status_code=400, detail="يجب إرسال مرجع معاملة حقيقي من مزود الدفع")

    result = await db.execute(
        select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id)
    )
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    if reg.processed:
        return {"ok": True, "paid": True, "processed": True, "detail": "تمت معالجة الطلب مسبقاً"}
    duplicate = await db.execute(
        select(models.RegistrationRequest).where(
            models.RegistrationRequest.payment_ref == payment_ref.strip(),
            models.RegistrationRequest.id != reg_id,
        ).limit(1)
    )
    if duplicate.scalars().first():
        raise HTTPException(status_code=409, detail="مرجع المعاملة مستخدم في طلب آخر")
    if reg.paid:
        if reg.payment_ref == payment_ref.strip():
            return {"ok": True, "paid": True, "processed": False, "detail": "إشعار الدفع سبق استلامه"}
        raise HTTPException(status_code=409, detail="تم تسجيل دفعة مختلفة لهذا الطلب؛ يلزم التحقق اليدوي")

    reg.paid = True
    reg.payment_ref = payment_ref.strip()
    db.add(models.AuditLog(
        action="webhook_payment_confirmed",
        performed_by="payment_gateway",
        details=f"Trusted callback marked registration #{reg_id} paid; awaiting administrator review",
    ))
    await db.commit()
    return {
        "ok": True,
        "username": reg.username,
        "paid": True,
        "processed": False,
        "message": "تم تسجيل إشعار الدفع، والطلب بانتظار مراجعة الإدارة قبل تفعيل الحساب.",
    }


@router.get('/registrations/{reg_id}/status')
async def registration_status(
    reg_id: int,
    x_registration_token: Optional[str] = Header(None, alias="X-Registration-Token"),
    db: AsyncSession = Depends(database.get_db),
):
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    _require_registration_token(reg, x_registration_token)

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
        "receipt_uploaded": bool(reg.receipt_image),
        "payment_message": latest_message.message if latest_message else None,
    }


@router.post('/registrations/{reg_id}/receipt')
async def upload_registration_receipt(
    reg_id: int,
    file: UploadFile = File(...),
    x_registration_token: Optional[str] = Header(None, alias="X-Registration-Token"),
    db: AsyncSession = Depends(database.get_db),
):
    """Store a private remittance image for manual review; never marks it paid."""
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg:
        raise HTTPException(status_code=404, detail="طلب التسجيل غير موجود")
    _require_registration_token(reg, x_registration_token)
    if reg.paid or reg.processed:
        raise HTTPException(status_code=409, detail="لا يمكن تعديل إيصال طلب تم تأكيد دفعه أو معالجته")

    allowed_types = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="يسمح فقط بملفات JPG أو PNG أو WEBP")

    contents = await file.read()
    if not contents or len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="حجم الصورة يجب ألا يتجاوز 5 ميجابايت")
    try:
        image = Image.open(BytesIO(contents))
        image.verify()
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Unsupported image format")
    except Exception:
        raise HTTPException(status_code=400, detail="الملف المرفوع ليس صورة سليمة")

    receipts_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    unique_filename = f"receipt_{reg.id}_{uuid.uuid4().hex[:12]}{allowed_types[file.content_type]}"
    target_path = receipts_dir / unique_filename
    with open(target_path, "wb") as output:
        output.write(contents)

    rel_path = f"uploads/receipts/{unique_filename}"
    reg.receipt_image = rel_path
    db.add(models.AuditLog(
        action="receipt_uploaded",
        performed_by=f"registration:{reg.id}",
        details=f"Private remittance image uploaded for registration #{reg.id}",
    ))
    await db.commit()
    return {
        "ok": True,
        "receipt_uploaded": True,
        "processed": False,
        "paid": False,
        "message": "تم استلام صورة الحوالة. ستراجعها الإدارة، ولا يتم تفعيل الاشتراك اعتماداً على الصورة وحدها.",
    }


@router.get('/registrations/{reg_id}/receipt')
async def get_registration_receipt(
    reg_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    """Serve remittance images only to authenticated administrators."""
    result = await db.execute(select(models.RegistrationRequest).where(models.RegistrationRequest.id == reg_id))
    reg = result.scalars().first()
    if not reg or not reg.receipt_image:
        raise HTTPException(status_code=404, detail="إيصال الحوالة غير موجود")
    backend_root = Path(__file__).resolve().parent.parent.parent
    receipts_root = (backend_root / "uploads" / "receipts").resolve()
    receipt_path = (backend_root / reg.receipt_image).resolve()
    if receipts_root not in receipt_path.parents or not receipt_path.is_file():
        raise HTTPException(status_code=404, detail="ملف الإيصال غير متاح")
    return FileResponse(str(receipt_path), media_type="application/octet-stream", filename=receipt_path.name)


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
    """Get the current status of the subscription notification agent."""
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
        "mode": "تنبيهات ومتابعة الطلبات؛ الاعتماد النهائي يدوي" if enabled else "إيقاف مؤقت",
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
    """Trigger a reminder/status scan; this action never approves payments or clients."""
    await process_pending_registrations(db, force_now=True)
    return {
        "ok": True,
        "notifications_checked": True,
        "message": "اكتمل فحص الطلبات وإرسال التنبيهات. لا يتم تفعيل أي حساب تلقائياً؛ راجع الدفعات واعتمدها يدوياً بعد التحقق."
    }

