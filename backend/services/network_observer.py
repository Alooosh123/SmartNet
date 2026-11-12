import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from config.settings import settings
from database import models
from services.mikrotik_service import mikrotik_service

logger = logging.getLogger(__name__)


def _int_or_none(value: Any):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def evaluate_snapshot(snapshot: dict) -> tuple[str, list[str]]:
    alerts: list[str] = []
    if snapshot.get("status") != "online":
        return "degraded", ["تعذر الوصول إلى MikroTik أو قراءة بياناته."]

    cpu = _int_or_none(snapshot.get("cpu_load"))
    if cpu is not None and cpu >= settings.NETWORK_CPU_ALERT_THRESHOLD:
        alerts.append(f"استخدام المعالج مرتفع: {cpu}%.")

    free_memory = _int_or_none(snapshot.get("free_memory_bytes"))
    total_memory = _int_or_none(snapshot.get("total_memory_bytes"))
    if free_memory is not None and total_memory and total_memory > 0:
        free_percent = free_memory / total_memory * 100
        if free_percent <= settings.NETWORK_FREE_MEMORY_ALERT_PERCENT:
            alerts.append(f"الذاكرة الحرة منخفضة: {free_percent:.1f}%.")

    return ("warning" if alerts else "healthy"), alerts


async def collect_and_store(session) -> models.NetworkMetric:
    try:
        snapshot = await asyncio.to_thread(mikrotik_service.monitor_snapshot)
        status_value, alerts = evaluate_snapshot(snapshot)
    except Exception:
        logger.exception("Network observer collection failed")
        snapshot = {"status": "unreachable"}
        status_value, alerts = evaluate_snapshot(snapshot)

    metric = models.NetworkMetric(
        status=status_value,
        board_name=str(snapshot.get("board_name") or "")[:128] or None,
        uptime=str(snapshot.get("uptime") or "")[:128] or None,
        cpu_load=_int_or_none(snapshot.get("cpu_load")),
        free_memory_bytes=_int_or_none(snapshot.get("free_memory_bytes")),
        total_memory_bytes=_int_or_none(snapshot.get("total_memory_bytes")),
        active_users_count=_int_or_none(snapshot.get("active_users_count")),
        alert_summary="\n".join(alerts) or None,
        observed_at=datetime.now(timezone.utc),
    )
    session.add(metric)
    await session.commit()
    await session.refresh(metric)
    return metric


async def latest_metrics(session, limit: int = 50):
    result = await session.execute(
        select(models.NetworkMetric)
        .order_by(models.NetworkMetric.observed_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    return result.scalars().all()


async def network_monitor_loop(stop_event: asyncio.Event) -> None:
    from database.database import AsyncSessionLocal

    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                await collect_and_store(session)
        except Exception:
            logger.exception("Network monitor cycle failed")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(15, settings.NETWORK_MONITOR_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            continue
