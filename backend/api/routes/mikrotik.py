from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_current_admin, get_current_user
from config.settings import settings
from database import database, models
from services.mikrotik_service import mikrotik_service

router = APIRouter(prefix="/mikrotik", tags=["mikrotik"])


class OperationRequest(BaseModel):
    action: Literal["disconnect_user", "reboot_router"]
    target: Optional[str] = Field(default=None, max_length=160)
    idempotency_key: Optional[str] = Field(default=None, min_length=12, max_length=80)


class OperationReview(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class DiagnosticRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1500)


def _authorize_request(current_user: dict, action: str) -> None:
    if current_user.get("role") == "admin":
        return
    client_obj = current_user.get("obj")
    plan = getattr(client_obj, "plan", "monthly") or "monthly"
    if action == "disconnect_user" and plan not in {"semi_annual", "annual"}:
        raise HTTPException(status_code=403, detail="طلب فصل المستخدمين متاح للباقة النصف سنوية والسنوية.")
    if action == "reboot_router" and not (
        getattr(client_obj, "can_reboot_network", False) or plan == "annual"
    ):
        raise HTTPException(status_code=403, detail="طلب إعادة التشغيل متاح للباقة السنوية فقط.")


async def _create_operation(
    action: str,
    target: Optional[str],
    idempotency_key: Optional[str],
    current_user: dict,
    db: AsyncSession,
):
    _authorize_request(current_user, action)
    if action == "disconnect_user" and not (target or "").strip():
        raise HTTPException(status_code=400, detail="اسم مستخدم الشبكة مطلوب للفصل.")
    if action == "reboot_router":
        target = None

    actor = current_user.get("username", "unknown")
    key = (idempotency_key or secrets.token_urlsafe(24)).strip()
    existing = await db.execute(
        select(models.NetworkOperation).where(models.NetworkOperation.idempotency_key == key)
    )
    operation = existing.scalars().first()
    if operation:
        if operation.requested_by != actor or operation.action != action or operation.target != target:
            raise HTTPException(status_code=409, detail="مفتاح منع التكرار مستخدم لطلب مختلف.")
        return operation

    operation = models.NetworkOperation(
        action=action,
        target=target.strip() if target else None,
        payload={"target": target.strip()} if target else {},
        status="pending",
        requested_by=actor,
        idempotency_key=key,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db.add(operation)
    db.add(models.AuditLog(
        action="network_operation_requested",
        performed_by=actor,
        details=f"Requested {action}; target={target or '-'}; request pending approval",
    ))
    await db.commit()
    await db.refresh(operation)
    return operation


@router.get("/status")
def get_router_status(current_user: dict = Depends(get_current_user)):
    """Read-only router status."""
    try:
        return mikrotik_service.get_status()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر الاتصال بالراوتر. راجع إعدادات الاتصال والسجلات.")


@router.get("/profiles")
def get_router_profiles(current_user: dict = Depends(get_current_admin)):
    """Return the available Hotspot profiles; this endpoint is read-only."""
    try:
        return mikrotik_service.get_profiles()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر قراءة ملفات Profile من الراوتر.")


@router.get("/users")
def get_active_users(current_user: dict = Depends(get_current_user)):
    role = current_user.get("role")
    client_obj = current_user.get("obj")
    if role != "admin":
        plan = getattr(client_obj, "plan", "monthly") or "monthly"
        if plan not in {"semi_annual", "annual"}:
            raise HTTPException(status_code=403, detail="عرض المستخدمين النشطين يتطلب الباقة النصف سنوية أو السنوية.")
    try:
        return mikrotik_service.get_active_users()
    except Exception:
        raise HTTPException(status_code=503, detail="تعذر قراءة الجلسات النشطة من الراوتر.")


@router.post("/operations", status_code=status.HTTP_202_ACCEPTED)
async def request_network_operation(
    payload: OperationRequest,
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    operation = await _create_operation(
        payload.action, payload.target, payload.idempotency_key, current_user, db
    )
    return {
        "ok": True,
        "operation_id": operation.id,
        "status": operation.status,
        "message": "تم تسجيل طلب العملية. لن يتم تنفيذها قبل اعتماد مسؤول مخول.",
    }


@router.get("/operations")
async def list_network_operations(
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    query = select(models.NetworkOperation).order_by(models.NetworkOperation.id.desc()).limit(200)
    if current_user.get("role") != "admin":
        query = query.where(models.NetworkOperation.requested_by == current_user.get("username"))
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": row.id,
            "action": row.action,
            "target": row.target,
            "status": row.status,
            "requested_by": row.requested_by,
            "reviewed_by": row.reviewed_by,
            "executed_by": row.executed_by,
            "review_note": row.review_note,
            "result": row.result,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
        }
        for row in rows
    ]


@router.post("/operations/{operation_id}/approve")
async def approve_network_operation(
    operation_id: int,
    payload: OperationReview,
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    row = (await db.execute(
        select(models.NetworkOperation).where(models.NetworkOperation.id == operation_id).with_for_update()
    )).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"لا يمكن اعتماد طلب حالته {row.status}.")
    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= now:
        row.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="انتهت صلاحية طلب العملية.")
    reviewer = getattr(current_admin, "username", "admin")
    if row.requested_by == reviewer and row.action == "reboot_router":
        raise HTTPException(status_code=409, detail="إعادة تشغيل الراوتر تتطلب اعتماد مسؤول آخر غير مقدم الطلب.")
    row.status = "approved"
    row.reviewed_by = reviewer
    row.reviewed_at = now
    row.review_note = (payload.note or "").strip() or None
    db.add(models.AuditLog(
        action="network_operation_approved",
        performed_by=reviewer,
        details=f"Approved network operation #{row.id}: {row.action}",
    ))
    await db.commit()
    return {"ok": True, "operation_id": row.id, "status": row.status, "message": "تم الاعتماد. يجب تنفيذ الطلب كخطوة مستقلة."}


@router.post("/operations/{operation_id}/reject")
async def reject_network_operation(
    operation_id: int,
    payload: OperationReview,
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    row = (await db.execute(
        select(models.NetworkOperation)
        .where(models.NetworkOperation.id == operation_id)
        .with_for_update()
    )).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="يمكن رفض الطلبات المعلقة فقط.")
    reviewer = getattr(current_admin, "username", "admin")
    row.status = "rejected"
    row.reviewed_by = reviewer
    row.reviewed_at = datetime.now(timezone.utc)
    row.review_note = (payload.note or "Rejected by administrator").strip()
    db.add(models.AuditLog(
        action="network_operation_rejected",
        performed_by=reviewer,
        details=f"Rejected network operation #{row.id}: {row.action}; {row.review_note}",
    ))
    await db.commit()
    return {"ok": True, "operation_id": row.id, "status": row.status}


@router.post("/operations/{operation_id}/execute")
async def execute_network_operation(
    operation_id: int,
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    # Lock the approval row while checking and claiming execution. This ensures
    # concurrent administrators cannot both dispatch the same RouterOS command.
    row = (await db.execute(
        select(models.NetworkOperation)
        .where(models.NetworkOperation.id == operation_id)
        .with_for_update()
    )).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="طلب العملية غير موجود.")
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="يجب اعتماد الطلب قبل التنفيذ.")
    actor = getattr(current_admin, "username", "admin")
    if row.requested_by == actor and row.action == "reboot_router":
        raise HTTPException(status_code=403, detail="لا يستطيع مقدم الطلب تنفيذ طلب إعادة تشغيل الراوتر بنفسه.")
    if row.expires_at:
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            row.status = "expired"
            await db.commit()
            raise HTTPException(status_code=410, detail="انتهت صلاحية طلب العملية.")
    # Persist a one-way state transition before touching the router, preventing
    # concurrent duplicate executions after retries or double-clicks.
    row.status = "executing"
    row.executed_by = actor
    row.executed_at = datetime.now(timezone.utc)
    await db.commit()

    try:
        if row.action == "disconnect_user":
            success = mikrotik_service.disconnect_user(row.target or "")
            if not success:
                raise RuntimeError("المستخدم غير متصل أو تعذر فصله")
            result = {"ok": True, "message": f"تم فصل المستخدم {row.target}."}
        elif row.action == "reboot_router":
            result = mikrotik_service.reboot_router()
        else:
            raise RuntimeError("عملية غير مسموح بها")
        row.status = "executed"
        row.result = result
    except Exception as exc:
        row.status = "failed"
        row.result = {"ok": False, "message": str(exc)[:500]}
    db.add(models.AuditLog(
        action="network_operation_" + row.status,
        performed_by=actor,
        details=f"Operation #{row.id} action={row.action}; result={row.status}",
    ))
    await db.commit()
    return {"ok": row.status == "executed", "operation_id": row.id, "status": row.status, "result": row.result}


@router.post("/users/{name}/disconnect", status_code=status.HTTP_202_ACCEPTED)
async def disconnect_active_user(
    name: str,
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    operation = await _create_operation("disconnect_user", name, None, current_user, db)
    return {"ok": True, "operation_id": operation.id, "status": operation.status, "message": "تم إرسال طلب فصل المستخدم للموافقة."}


@router.post("/reboot", status_code=status.HTTP_202_ACCEPTED)
async def reboot_network_router(
    db: AsyncSession = Depends(database.get_db),
    current_user: dict = Depends(get_current_user),
):
    operation = await _create_operation("reboot_router", None, None, current_user, db)
    return {"ok": True, "operation_id": operation.id, "status": operation.status, "message": "تم تسجيل طلب إعادة التشغيل للمراجعة والاعتماد."}


@router.get("/monitor/snapshots")
async def list_network_snapshots(
    limit: int = 100,
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    limit = max(1, min(limit, 500))
    rows = (await db.execute(
        select(models.NetworkSnapshot).order_by(models.NetworkSnapshot.id.desc()).limit(limit)
    )).scalars().all()
    return rows


@router.get("/monitor/alerts")
async def list_network_alerts(
    db: AsyncSession = Depends(database.get_db),
    current_admin=Depends(get_current_admin),
):
    rows = (await db.execute(
        select(models.NetworkAlert).order_by(models.NetworkAlert.id.desc()).limit(200)
    )).scalars().all()
    return rows


@router.post("/diagnose")
async def diagnose_network(
    payload: DiagnosticRequest,
    current_admin=Depends(get_current_admin),
):
    from services.diagnostics_agent import diagnose
    return await diagnose(payload.question)
