"""Read-only network monitoring worker.

This agent only invokes MikroTik read operations. No write capability is imported
or exposed here. Router changes must use the approval endpoints in api.routes.mikrotik.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from config.settings import settings
from database import models
from database.database import AsyncSessionLocal
from services.mikrotik_service import mikrotik_service

logger = logging.getLogger(__name__)


def _int_or_none(value):
    try:
        return int(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None


async def _raise_alert(session, code: str, severity: str, message: str) -> None:
    now = datetime.now(timezone.utc)
    recent = await session.execute(
        select(models.NetworkAlert)
        .where(models.NetworkAlert.code == code, models.NetworkAlert.active.is_(True))
        .order_by(models.NetworkAlert.id.desc())
        .limit(1)
    )
    alert = recent.scalars().first()
    if alert is not None:
        created = alert.created_at
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created and now - created < timedelta(seconds=settings.NETWORK_ALERT_COOLDOWN_SECONDS):
            return
    session.add(models.NetworkAlert(code=code, severity=severity, message=message, active=True))


async def collect_network_snapshot(session) -> models.NetworkSnapshot:
    """Collect a single read-only RouterOS observation and evaluate safe thresholds."""
    status, active_users = await asyncio.gather(
        asyncio.to_thread(mikrotik_service.get_status),
        asyncio.to_thread(mikrotik_service.get_active_users),
    )
    cpu = _int_or_none(status.get("cpu-load", status.get("cpu_load", status.get("cpu"))))
    free_memory = _int_or_none(status.get("free-memory", status.get("free_memory")))
    total_memory = _int_or_none(status.get("total-memory", status.get("total_memory")))
    user_count = len(active_users or [])

    snapshot = models.NetworkSnapshot(
        cpu_load=cpu,
        free_memory=free_memory,
        total_memory=total_memory,
        active_users=user_count,
        router_uptime=str(status.get("uptime", ""))[:80] or None,
        router_version=str(status.get("version", ""))[:80] or None,
    )
    session.add(snapshot)

    if cpu is not None and cpu >= settings.NETWORK_CPU_ALERT_THRESHOLD:
        await _raise_alert(
            session, "router_cpu_high", "warning",
            f"Router CPU load is {cpu}%, above threshold {settings.NETWORK_CPU_ALERT_THRESHOLD}%.",
        )
    if user_count >= settings.NETWORK_ACTIVE_USERS_ALERT_THRESHOLD:
        await _raise_alert(
            session, "active_users_high", "warning",
            f"Active Hotspot users {user_count} reached threshold {settings.NETWORK_ACTIVE_USERS_ALERT_THRESHOLD}.",
        )

    # Resolve threshold alerts automatically when a later successful observation
    # shows the measured value has returned below its configured limit.
    active_alerts = await session.execute(
        select(models.NetworkAlert).where(models.NetworkAlert.active.is_(True))
    )
    for alert in active_alerts.scalars().all():
        if alert.code == "router_cpu_high" and cpu is not None and cpu < settings.NETWORK_CPU_ALERT_THRESHOLD:
            alert.active = False
            alert.resolved_at = datetime.now(timezone.utc)
        elif alert.code == "active_users_high" and user_count < settings.NETWORK_ACTIVE_USERS_ALERT_THRESHOLD:
            alert.active = False
            alert.resolved_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(snapshot)
    return snapshot


async def network_monitor_loop(stop_event: asyncio.Event) -> None:
    if not settings.NETWORK_MONITOR_ENABLED:
        logger.info("Read-only network monitoring agent is disabled.")
        return
    if settings.MIKROTIK_DEMO_MODE:
        logger.warning("Network monitoring agent will not run against demo MikroTik data.")
        return

    logger.info("Read-only network monitoring agent started.")
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                await collect_network_snapshot(session)
        except Exception:
            logger.exception("Read-only network monitoring collection failed.")
            try:
                async with AsyncSessionLocal() as session:
                    await _raise_alert(
                        session, "router_unreachable", "critical",
                        "SmartNet could not collect a read-only status snapshot from MikroTik.",
                    )
                    await session.commit()
            except Exception:
                logger.exception("Unable to persist network connectivity alert.")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(15, settings.NETWORK_MONITOR_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            pass

