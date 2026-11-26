"""Admin-only dispatcher for the allow-listed SmartNet n8n advisory agents."""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_admin
from config.settings import settings
from database import database, models
from services.n8n_agent_client import (
    AGENT_NAMES,
    AGENT_WEBHOOK_PATHS,
    BLOCKED_TASKS,
    TASK_TO_AGENT,
    N8nAgentTransportError,
    N8nIntegrationDisabled,
    invoke_agent,
)

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


def _validate_agent_payload(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("يجب أن تكون بيانات الوكيل كائن JSON.")
    if "request_id" in value or "task" in value:
        raise ValueError("الحقول task وrequest_id محجوزة ويتحكم بها الموزّع.")
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("بيانات الوكيل يجب أن تكون قابلة للتحويل إلى JSON.") from exc
    if len(serialized.encode("utf-8")) > 16_384:
        raise ValueError("حجم بيانات الوكيل يتجاوز 16 KiB.")
    if any(key in {"__proto__", "constructor", "prototype"} for key in value):
        raise ValueError("تحتوي بيانات الوكيل على مفتاح محجوز.")
    return value


class AgentInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=8, max_length=80)

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_agent_payload(value)


class AgentDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=8, max_length=80)

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_agent_payload(value)


def _audit(
    db: AsyncSession,
    admin_name: str,
    request_id: str,
    action: str,
    *,
    agent_id: str | None = None,
    status_value: str = "completed",
) -> None:
    """Write metadata only; never persist the request body, payment values or secrets."""
    details = {
        "request_id": request_id,
        "agent_id": agent_id,
        "status": status_value,
    }
    db.add(models.AuditLog(
        action=action,
        performed_by=admin_name,
        details=json.dumps(details, ensure_ascii=False)[:1900],
    ))


def _map_n8n_error(exc: Exception) -> HTTPException:
    if isinstance(exc, N8nIntegrationDisabled):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="تكامل وكلاء n8n غير مفعّل أو أن إعدادات الاتصال غير مكتملة.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="تعذر الوصول إلى وكيل SmartNet في n8n أو استلام استجابة صالحة.",
    )


@router.get("/agents")
async def list_automation_agents(_admin=Depends(get_current_admin)):
    """Return the static allow-list and whether the optional n8n bridge is configured."""
    return {
        "enabled": settings.N8N_ENABLED,
        "agents": [
            {
                "id": agent_id,
                "name": AGENT_NAMES[agent_id],
                "webhook_path": f"/webhook/{AGENT_WEBHOOK_PATHS[agent_id]}",
                "execution_mode": "read_only_advisory",
            }
            for agent_id in sorted(AGENT_WEBHOOK_PATHS)
        ],
        "tasks": sorted(TASK_TO_AGENT),
        "blocked_tasks": sorted(BLOCKED_TASKS),
    }


@router.post("/agents/{agent_id}/invoke")
async def invoke_specific_agent(
    agent_id: str,
    request: AgentInvokeRequest,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    """Invoke one allow-listed agent directly; only administrators may use this route."""
    if agent_id not in AGENT_WEBHOOK_PATHS:
        raise HTTPException(status_code=404, detail="وكيل SmartNet غير معروف.")

    body = {**request.payload, "request_id": request.request_id}
    try:
        result = await invoke_agent(agent_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (N8nIntegrationDisabled, N8nAgentTransportError) as exc:
        _audit(db, admin.username, request.request_id, "n8n_agent_invocation_failed", agent_id=agent_id, status_value="failed")
        await db.commit()
        raise _map_n8n_error(exc) from exc

    _audit(db, admin.username, request.request_id, "n8n_agent_invocation", agent_id=agent_id)
    await db.commit()
    return {
        "request_id": request.request_id,
        "agent_id": agent_id,
        "agent_name": AGENT_NAMES[agent_id],
        "result": result,
        "execution_authority": "read_only_advisory",
    }


@router.post("/dispatch")
async def dispatch_agent_task(
    request: AgentDispatchRequest,
    admin=Depends(get_current_admin),
    db: AsyncSession = Depends(database.get_db),
):
    """Ask supervisor 00 to classify a task, then invoke only its fixed allow-listed child."""
    try:
        supervisor = await invoke_agent("00", {
            "task": request.task,
            "request_id": request.request_id,
        })
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (N8nIntegrationDisabled, N8nAgentTransportError) as exc:
        _audit(db, admin.username, request.request_id, "n8n_supervisor_failed", status_value="failed")
        await db.commit()
        raise _map_n8n_error(exc) from exc

    supervisor_status = supervisor.get("status")
    if supervisor_status != "dispatch_ready":
        _audit(
            db,
            admin.username,
            request.request_id,
            "n8n_supervisor_gate",
            status_value=str(supervisor_status or "invalid_response"),
        )
        await db.commit()
        return {
            "request_id": request.request_id,
            "supervisor": supervisor,
            "agent_invoked": False,
            "execution_authority": "read_only_advisory",
        }

    expected_agent_id = TASK_TO_AGENT.get(request.task)
    expected_path = (
        f"/webhook/{AGENT_WEBHOOK_PATHS[expected_agent_id]}"
        if expected_agent_id
        else None
    )
    if (
        not expected_agent_id
        or supervisor.get("target_agent") != AGENT_WEBHOOK_PATHS[expected_agent_id].split("/")[-1]
        or supervisor.get("target_path") != expected_path
    ):
        _audit(
            db,
            admin.username,
            request.request_id,
            "n8n_supervisor_route_rejected",
            status_value="route_mismatch",
        )
        await db.commit()
        raise HTTPException(
            status_code=502,
            detail="أعاد المشرف مساراً لا يطابق قائمة وكلاء SmartNet المعتمدة؛ تم إيقاف الاستدعاء.",
        )

    child_payload = {
        **request.payload,
        "task": request.task,
        "request_id": request.request_id,
    }
    try:
        result = await invoke_agent(expected_agent_id, child_payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (N8nIntegrationDisabled, N8nAgentTransportError) as exc:
        _audit(
            db,
            admin.username,
            request.request_id,
            "n8n_child_agent_failed",
            agent_id=expected_agent_id,
            status_value="failed",
        )
        await db.commit()
        raise _map_n8n_error(exc) from exc

    _audit(
        db,
        admin.username,
        request.request_id,
        "n8n_supervised_agent_dispatch",
        agent_id=expected_agent_id,
    )
    await db.commit()
    return {
        "request_id": request.request_id,
        "supervisor": supervisor,
        "agent": {
            "id": expected_agent_id,
            "name": AGENT_NAMES[expected_agent_id],
            "result": result,
        },
        "execution_authority": "read_only_advisory",
        "side_effects_performed": False,
    }
