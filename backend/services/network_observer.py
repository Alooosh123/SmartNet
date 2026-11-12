"""Read-only periodic collector for MikroTik network health.

This agent only invokes get_status/get_active_users. It has no write methods and
never calls disconnect, card creation, or reboot operations.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import delete, select

from config.settings import settings
from database import models
from database.database import AsyncSessionLocal
from services.mikrotik_service import mikrotik_service

logger = logging.getLogger(__name__)


def _integer(value):
    if value is None:
        return None
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group(0)) if match else None


def _bytes_to_mb(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    number = _integer(text)
    if number is None:
        return None
    if "gib" in text or "gb" in text:
        return number * 1024
    if "mib" in text or "mb" in text:
        return number
    if "kib" in text or "kb" in text:
        return max(1, number // 1024)
    # RouterOS API returns free-memory as bytes.
    return max(0, number // (1024 * 1024))


async def collect_network_observation() -> dict:
    """Collect one snapshot without issuing any RouterOS mutation."""
    status_data = None
    users = None
    errors = []
    try:
        status_data = await asyncio.to_thread(mikrotik_service.get_status)
    except Exception as exc:
        errors.append(f"router status: {type(exc).__name__}")
    try:
        users = await asyncio.to_thread(mikrotik_service.get_active_users)
    except Exception as exc:
        errors.append(f"active users: {type(exc).__name__}")

    cpu = _integer((status_data or {}).get("cpu-load", (status_data or {}).get("cpu_load")))
    free_mb = _bytes_to_mb((status_data or {}).get("free-memory", (status_data or {}).get("free_memory")))
    users_count = len(users) if isinstance(users, list) else None
    warnings = []
    if cpu is not None and cpu >= settings.NETWORK_ALERT_CPU_THRESHOLD:
        warnings.append(f"High CPU usage: {cpu}%")
    if free_mb is not None and free_mb <= settings.NETWORK_ALERT_FREE_MEMORY_MB:
        warnings.append(f"Low free memory: {free_mb} MB")
    if errors:
        warnings.extend(errors)

    if errors and status_data is None:
        health = "offline"
    elif warnings:
        health = "warning"
    else:
        health = "healthy"

    detail_parts = []
    if errors:
        detail_parts.append("; ".join(errors))
    detail_parts.append("Collected using read-only RouterOS resource and active-session queries.")
    snapshot = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": health,
        "router_board": (status_data or {}).get("board-name") or (status_data or {}).get("board_name"),
        "router_version": (status_data or {}).get("version"),
        "cpu_load": cpu,
        "free_memory_mb": free_mb,
        "active_users_count": users_count,
        "warning": "; ".join(warnings)[:500] if warnings else None,
        "detail": " ".join(detail_parts)[:1000],
    }

    async with AsyncSessionLocal() as session:
        session.add(models.NetworkObservation(**snapshot))
        await session.commit()

        result = await session.execute(
            select(models.NetworkObservation.id)
            .order_by(models.NetworkObservation.id.desc())
            .offset(settings.NETWORK_OBSERVER_HISTORY_LIMIT)
        )
        old_ids = [row[0] for row in result.fetchall()]
        if old_ids:
            await session.execute(
                delete(models.NetworkObservation).where(models.NetworkObservation.id.in_(old_ids))
            )
            await session.commit()
    return snapshot


async def network_observer_loop(stop_event: asyncio.Event) -> None:
    logger.info("SmartNet read-only Network Observer started.")
    while not stop_event.is_set():
        if settings.NETWORK_OBSERVER_ENABLED:
            try:
                await collect_network_observation()
            except Exception:
                logger.exception("Network Observer cycle failed.")
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(15, settings.NETWORK_OBSERVER_INTERVAL_SECONDS),
            )
        except asyncio.TimeoutError:
            continue
    logger.info("SmartNet read-only Network Observer stopped.")
