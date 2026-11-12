import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_current_user, get_current_admin
from database import database, models
from services.mikrotik_service import mikrotik_service
from services.network_diagnostic_agent import diagnose_latest_network
from config.settings import settings

router = APIRouter(prefix="/mikrotik", tags=["mikrotik"])


def _client_plan(user: dict) -> str:
    client = user.get("obj")
    return getattr(client, "plan", "monthly") or "monthly"


@router.get("/status")
def get_router_status(current_user: dict = Depends(get_current_user)):
    """Authenticated users may view aggregate router status."""
    try:
        return mikrotik_service.get_status()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر قراءة حالة الراوتر. تحقق من اتصال MikroTik.")


@router.get("/users")
def get_active_users(current_admin=Depends(get_current_admin)):
    """Active subscriber identities and IP/MAC details are administrator-only."""
    try:
        return mikrotik_service.get_active_users()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر قراءة الجلسات النشطة من الراوتر.")


@router.post("/users/{name}/disconnect")
async def disconnect_active_user(
    name: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db),
):
    """Admins execute; eligible customers can only request a reviewed disconnection."""
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="اسم المستخدم غير صالح.")

    if current_user.get("role") == "admin":
        try:
            success = await asyncio.to_thread(mikrotik_service.disconnect_user, name)
        except Exception:
            raise HTTPException(status_code=503, detail="فشل الاتصال بالراوتر لتنفيذ الفصل.")
        if not success:
            raise HTTPException(status_code=404, detail="المستخدم غير متصل أو تعذر فصله")
        db.add(models.AuditLog(
            action="network_disconnect_executed",
            performed_by=current_user.get("username", "admin"),
            details=f"Administrator disconnected hotspot user {name}.",
        ))
        await db.commit()
        return {"ok": True, "status": "executed", "message": f"تم فصل المستخدم {name} بنجاح."}

    plan = _client_plan(current_user)
    if plan not in {"semi_annual", "annual"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="طلب فصل المستخدمين متاح للباقة نصف السنوية والسنوية فقط.",
        )

    request = models.NetworkActionRequest(
        action="disconnect_user",
        target=name,
        requested_by=current_user.get("username", "client"),
        reason="طلب فصل جلسة من مشترك؛ يتطلب موافقة مشغل الشبكة.",
        status="pending",
    )
    db.add(request)
    db.add(models.AuditLog(
        action="network_action_requested",
        performed_by=current_user.get("username", "client"),
        details=f"Requested disconnect for hotspot user {name}; pending admin approval.",
    ))
    await db.commit()
    await db.refresh(request)
    return {
        "ok": True,
        "status": "pending",
        "request_id": request.id,
        "message": "تم إرسال طلب الفصل إلى إدارة الشبكة للمراجعة والموافقة.",
    }


@router.post("/reboot")
async def reboot_network_router(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(database.get_db),
):
    """Only administrators execute router reboot; annual subscribers may request it."""
    if current_user.get("role") == "admin":
        try:
            result = await asyncio.to_thread(mikrotik_service.reboot_router)
        except Exception:
            raise HTTPException(status_code=503, detail="فشل الاتصال بالراوتر لتنفيذ إعادة التشغيل.")
        db.add(models.AuditLog(
            action="network_reboot_executed",
            performed_by=current_user.get("username", "admin"),
            details="Administrator executed router reboot from the control panel.",
        ))
        await db.commit()
        return {"ok": True, "status": "executed", **result}

    if _client_plan(current_user) != "annual":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="يمكن لمشتركي الباقة السنوية طلب إعادة تشغيل الشبكة بعد موافقة الإدارة.",
        )

    request = models.NetworkActionRequest(
        action="reboot_router",
        target=None,
        requested_by=current_user.get("username", "client"),
        reason="طلب إعادة تشغيل الشبكة من مشترك سنوي؛ يتطلب موافقة مشغل الشبكة.",
        status="pending",
    )
    db.add(request)
    db.add(models.AuditLog(
        action="network_action_requested",
        performed_by=current_user.get("username", "client"),
        details="Requested router reboot; pending admin approval.",
    ))
    await db.commit()
    await db.refresh(request)
    return {
        "ok": True,
        "status": "pending",
        "request_id": request.id,
        "message": "تم إرسال طلب إعادة تشغيل الراوتر إلى الإدارة. لن يتم التنفيذ قبل الموافقة.",
    }


@router.get("/action-requests")
async def list_network_action_requests(
    current_admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    result = await db.execute(
        select(models.NetworkActionRequest).order_by(models.NetworkActionRequest.id.desc()).limit(500)
    )
    return result.scalars().all()


@router.post("/action-requests/{request_id}/approve")
async def approve_network_action(
    request_id: int,
    review_note: Optional[str] = None,
    current_admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    result = await db.execute(
        select(models.NetworkActionRequest).where(models.NetworkActionRequest.id == request_id).with_for_update()
    )
    request = result.scalars().first()
    if request is None:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="تمت مراجعة هذا الطلب مسبقاً.")
    reviewer = getattr(current_admin, "username", "admin")
    if request.requested_by == reviewer:
        raise HTTPException(status_code=409, detail="لا يجوز اعتماد طلب العملية بواسطة نفس منشئه.")
    if request.action not in {"reboot_router", "disconnect_user"}:
        raise HTTPException(status_code=400, detail="نوع العملية غير مدعوم.")

    try:
        if request.action == "reboot_router":
            execution = await asyncio.to_thread(mikrotik_service.reboot_router)
            succeeded = bool(execution.get("ok"))
        elif request.action == "disconnect_user" and request.target:
            succeeded = await asyncio.to_thread(mikrotik_service.disconnect_user, request.target)
            execution = {"ok": succeeded, "message": "disconnect executed" if succeeded else "session not found"}
    except Exception:
        request.status = "failed"
        request.reviewed_by = reviewer
        request.reviewed_at = datetime.now(timezone.utc)
        request.result = "Router operation failed; check protected server logs."
        db.add(models.AuditLog(
            action="network_action_failed",
            performed_by=reviewer,
            details=f"Action request #{request.id} failed during execution.",
        ))
        await db.commit()
        raise HTTPException(status_code=503, detail="تعذر تنفيذ العملية على الراوتر.")

    request.reviewed_by = reviewer
    request.review_note = (review_note or "").strip()[:500] or None
    request.reviewed_at = datetime.now(timezone.utc)
    request.executed_at = datetime.now(timezone.utc) if succeeded else None
    request.status = "executed" if succeeded else "failed"
    request.result = str(execution.get("message", "completed"))[:1000]
    db.add(models.AuditLog(
        action="network_action_approved" if succeeded else "network_action_failed",
        performed_by=reviewer,
        details=f"Reviewed request #{request.id} ({request.action}) requested by {request.requested_by}; status={request.status}.",
    ))
    await db.commit()
    await db.refresh(request)
    return {"ok": succeeded, "request": request}


@router.post("/action-requests/{request_id}/reject")
async def reject_network_action(
    request_id: int,
    reason: str,
    current_admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    rejection_reason = (reason or "").strip()
    if len(rejection_reason) < 6 or len(rejection_reason) > 500:
        raise HTTPException(status_code=400, detail="يجب إدخال سبب رفض من 6 إلى 500 حرف.")
    result = await db.execute(
        select(models.NetworkActionRequest).where(models.NetworkActionRequest.id == request_id)
    )
    request = result.scalars().first()
    if request is None:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail="تمت مراجعة هذا الطلب مسبقاً.")
    reviewer = getattr(current_admin, "username", "admin")
    if request.requested_by == reviewer:
        raise HTTPException(status_code=409, detail="لا يجوز رفض طلب العملية بواسطة نفس منشئه.")
    request.status = "rejected"
    request.reviewed_by = reviewer
    request.review_note = rejection_reason
    request.reviewed_at = datetime.now(timezone.utc)
    db.add(models.AuditLog(
        action="network_action_rejected",
        performed_by=reviewer,
        details=f"Rejected request #{request.id} ({request.action}) requested by {request.requested_by}: {rejection_reason}",
    ))
    await db.commit()
    await db.refresh(request)
    return {"ok": True, "request": request}


@router.get("/observations")
async def get_network_observations(
    current_admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    result = await db.execute(
        select(models.NetworkObservation)
        .order_by(models.NetworkObservation.id.desc())
        .limit(settings.NETWORK_OBSERVER_HISTORY_LIMIT)
    )
    return result.scalars().all()


@router.post("/diagnostics")
async def request_network_diagnosis(
    question: str,
    current_admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    if not question.strip() or len(question) > 1000:
        raise HTTPException(status_code=400, detail="اكتب وصفاً للمشكلة لا يتجاوز 1000 حرف.")
    try:
        return await diagnose_latest_network(db, question.strip())
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر إعداد تقرير التشخيص. راجع بيانات المراقبة وسجلات الخادم.")
