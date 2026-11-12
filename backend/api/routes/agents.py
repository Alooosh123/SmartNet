from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_admin
from database import database, models
from services.network_observer import collect_and_store, latest_metrics
from services.diagnostic_agent import diagnose

router = APIRouter(prefix="/agents", tags=["AI and Network Agents"])


def _metric_payload(metric: models.NetworkMetric) -> dict:
    return {
        "id": metric.id,
        "observed_at": metric.observed_at.isoformat() if metric.observed_at else None,
        "status": metric.status, "board_name": metric.board_name, "uptime": metric.uptime,
        "cpu_load": metric.cpu_load, "free_memory_bytes": metric.free_memory_bytes,
        "total_memory_bytes": metric.total_memory_bytes,
        "active_users_count": metric.active_users_count,
        "alerts": metric.alert_summary.splitlines() if metric.alert_summary else [],
    }


@router.get("/network/overview")
async def network_overview(db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    result = await latest_metrics(db, limit=1)
    latest = result[0] if result else None
    return {
        "monitoring_enabled": True,
        "latest": _metric_payload(latest) if latest else None,
        "agent_mode": "read-only",
        "router_commands_allowed": False,
    }


@router.get("/network/history")
async def network_history(limit: int = 50, db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    metrics = await latest_metrics(db, limit=max(1, min(limit, 500)))
    return [_metric_payload(item) for item in metrics]


@router.post("/network/collect")
async def collect_network_snapshot(db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    metric = await collect_and_store(db)
    return _metric_payload(metric)


@router.post("/diagnostics/run")
async def run_diagnostics(db: AsyncSession = Depends(database.get_db), current_admin=Depends(get_current_admin)):
    metric = await collect_and_store(db)
    return diagnose(metric)
