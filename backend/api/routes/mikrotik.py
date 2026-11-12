from datetime import datetime, timedelta, timezone
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_current_admin
from database import database, models, schemas
from services.mikrotik_service import mikrotik_service

router = APIRouter(prefix="/mikrotik", tags=["mikrotik"])


def _serialize_request(item: models.NetworkActionRequest) -> dict:
    return {
        "id": item.id, "action_type": item.action_type, "target_user": item.target_user,
        "requested_by": item.requested_by, "requested_role": item.requested_role,
        "reason": item.reason, "status": item.status, "approved_by": item.approved_by,
        "approval_note": item.approval_note, "result_summary": item.result_summary,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "executed_at": item.executed_at.isoformat() if item.executed_at else None,
    }


def _require_plan_for_request(current_user: dict, action_type: str) -> None:
    if current_user.get("role") == "admin":
        return
    plan = getattr(current_user.get("obj"), "plan", "monthly") or "monthly"
    if plan not in {"semi_annual", "annual"}:
        raise HTTPException(status_code=403, detail="هذه العملية تتطلب باقة نصف سنوية أو سنوية.")
    if action_type == "reboot" and plan != "annual":
        raise HTTPException(status_code=403, detail="طلب إعادة تشغيل الشبكة متاح للباقة السنوية فقط.")


async def _create_action_request(payload: schemas.NetworkActionRequestCreate, current_user: dict, db: AsyncSession):
    if payload.action_type == "disconnect" and not payload.target_user:
        raise HTTPException(status_code=422, detail="اسم المستخدم المستهدف مطلوب لفصل الجلسة.")
    _require_plan_for_request(current_user, payload.action_type)
    request = models.NetworkActionRequest(
        action_type=payload.action_type, target_user=payload.target_user,
        requested_by=current_user.get("username", "unknown"),
        requested_role=current_user.get("role", "client"), reason=payload.reason,
        status="pending", expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(request)
    db.add(models.AuditLog(
        action="network_action_requested", performed_by=request.requested_by,
        details=f"Requested {request.action_type}; approval required. Reason: {request.reason[:300]}",
    ))
    await db.commit()
    await db.refresh(request)
    return request


@router.get("/status")
def get_router_status(current_user: dict = Depends(get_current_user)):
    try:
        return mikrotik_service.get_status()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر الوصول إلى الراوتر. راجع إعدادات الاتصال والسجلات.")


@router.get("/users")
def get_active_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        plan = getattr(current_user.get("obj"), "plan", "monthly") or "monthly"
        if plan not in {"semi_annual", "annual"}:
            raise HTTPException(status_code=403, detail="عرض قائمة المستخدمين يتطلب باقة نصف سنوية أو سنوية.")
    try:
        return mikrotik_service.get_active_users()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر قراءة جلسات MikroTik.")


@router.post("/action-requests")
async def create_network_action_request(payload: schemas.NetworkActionRequestCreate, db: AsyncSession = Depends(database.get_db), current_user: dict = Depends(get_current_user)):
    request = await _create_action_request(payload, current_user, db)
    return _serialize_request(request)


@router.get("/action-requests")
async def list_network_action_requests(db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    result = await db.execute(select(models.NetworkActionRequest).order_by(models.NetworkActionRequest.id.desc()).limit(200))
    return [_serialize_request(item) for item in result.scalars().all()]


@router.post("/action-requests/{request_id}/approve")
async def approve_network_action_request(
    request_id: int, payload: dict | None = None,
    db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin),
):
    result = await db.execute(select(models.NetworkActionRequest).where(models.NetworkActionRequest.id == request_id).with_for_update())
    request = result.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"الطلب ليس في حالة انتظار (الحالة: {request.status}).")
    now = datetime.now(timezone.utc)
    expires = request.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        request.status = "expired"
        db.add(models.AuditLog(action="network_action_expired", performed_by="system", details=f"Request #{request.id} expired"))
        await db.commit()
        raise HTTPException(status_code=409, detail="انتهت صلاحية طلب العملية.")
    approver = getattr(current_admin, "username", "admin")
    if request.requested_role == "admin" and request.requested_by == approver:
        raise HTTPException(status_code=403, detail="يجب أن يعتمد الطلب مسؤول آخر غير منشئه.")

    request.status = "approved"
    request.approved_by = approver
    request.approval_note = (payload or {}).get("note")
    request.approved_at = now
    db.add(models.AuditLog(action="network_action_approved", performed_by=approver, details=f"Approved request #{request.id} ({request.action_type})"))
    await db.commit()

    try:
        if request.action_type == "reboot":
            result_data = await asyncio.to_thread(mikrotik_service.reboot_router)
        elif request.action_type == "disconnect":
            disconnected = await asyncio.to_thread(mikrotik_service.disconnect_user, request.target_user)
            if not disconnected:
                raise RuntimeError("المستخدم غير متصل أو لم يتم العثور على الجلسة.")
            result_data = {"ok": True, "message": "تم فصل الجلسة."}
        else:
            raise RuntimeError("نوع العملية غير مدعوم.")
        request.status = "executed"
        request.result_summary = str(result_data.get("message", "Executed"))[:1000]
    except Exception as exc:
        request.status = "failed"
        request.result_summary = str(exc)[:1000]
        db.add(models.AuditLog(action="network_action_failed", performed_by=approver, details=f"Request #{request.id}: {str(exc)[:500]}"))
    request.executed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(request)
    return _serialize_request(request)


@router.post("/action-requests/{request_id}/reject")
async def reject_network_action_request(request_id: int, payload: dict | None = None, db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    result = await db.execute(select(models.NetworkActionRequest).where(models.NetworkActionRequest.id == request_id))
    request = result.scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="لا يمكن رفض طلب تمت معالجته.")
    request.status = "rejected"
    request.approved_by = getattr(current_admin, "username", "admin")
    request.approval_note = (payload or {}).get("note") or "Rejected by administrator"
    db.add(models.AuditLog(action="network_action_rejected", performed_by=request.approved_by, details=f"Rejected request #{request.id}: {request.approval_note[:500]}"))
    await db.commit()
    await db.refresh(request)
    return _serialize_request(request)


@router.post("/users/{name}/disconnect")
async def request_disconnect(name: str, db: AsyncSession = Depends(database.get_db), current_user: dict = Depends(get_current_user)):
    payload = schemas.NetworkActionRequestCreate(action_type="disconnect", target_user=name, reason="طلب فصل جلسة: " + name)
    request = await _create_action_request(payload, current_user, db)
    return {"ok": True, "status": "pending_approval", "request_id": request.id, "message": "تم تسجيل طلب الفصل وينتظر اعتماد مسؤول مخول."}


@router.post("/reboot")
async def request_reboot(db: AsyncSession = Depends(database.get_db), current_user: dict = Depends(get_current_user)):
    payload = schemas.NetworkActionRequestCreate(action_type="reboot", reason="طلب إعادة تشغيل الراوتر")
    request = await _create_action_request(payload, current_user, db)
    return {"ok": True, "status": "pending_approval", "request_id": request.id, "message": "تم تسجيل طلب إعادة التشغيل وينتظر اعتماد مسؤول آخر."}
