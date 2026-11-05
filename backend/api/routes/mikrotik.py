from fastapi import APIRouter, Depends, HTTPException, status
from api.dependencies import get_current_user
from services.mikrotik_service import mikrotik_service

router = APIRouter(prefix="/mikrotik", tags=["mikrotik"])


@router.get("/status")
def get_router_status(current_user: dict = Depends(get_current_user)):
    """All authenticated admins and clients can view router health status."""
    try:
        return mikrotik_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users")
def get_active_users(current_user: dict = Depends(get_current_user)):
    """Admin or clients with Semi-Annual or Annual plans can view active network users."""
    role = current_user.get("role")
    client_obj = current_user.get("obj")

    if role != "admin":
        plan = getattr(client_obj, "plan", "monthly") or "monthly"
        if plan == "monthly":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="عرض قائمة المستخدمين النشطين يتطلب باقة نصف سنوية ($60) أو سنوية ($100)."
            )

    try:
        return mikrotik_service.get_active_users()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{name}/disconnect")
def disconnect_active_user(name: str, current_user: dict = Depends(get_current_user)):
    """Admin or clients with Semi-Annual or Annual plans can disconnect active users."""
    role = current_user.get("role")
    client_obj = current_user.get("obj")

    if role != "admin":
        plan = getattr(client_obj, "plan", "monthly") or "monthly"
        if plan == "monthly":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="صلاحية فصل المستخدمين من الشبكة مخصصة لمشتركي الباقات النصف سنوية والسنوية."
            )

    try:
        success = mikrotik_service.disconnect_user(name=name)
        if not success:
            raise HTTPException(status_code=404, detail="المستخدم غير متصل أو تعذر فصله")
        return {"ok": True, "message": f"تم فصل المستخدم {name} بنجاح"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reboot")
def reboot_network_router(current_user: dict = Depends(get_current_user)):
    """Only Admins and Clients on the Annual Plan ($100) have network reboot privileges."""
    role = current_user.get("role")
    client_obj = current_user.get("obj")

    if role != "admin":
        can_reboot = getattr(client_obj, "can_reboot_network", False)
        plan = getattr(client_obj, "plan", "monthly") or "monthly"
        if not can_reboot and plan != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="صلاحية إعادة تشغيل شبكة الراوتر (Reboot) حصرية لمشتركي الباقة السنوية ($100) أو إدارة النظام."
            )

    try:
        result = mikrotik_service.reboot_router()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"فشل إرسال أمر إعادة التشغيل: {str(e)}")



