import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import settings
from database import models
from database.database import Base
from services import network_monitor_agent
from services.diagnostics_agent import collect_read_only_observations, search_knowledge_base


def test_diagnostics_agent_retrieves_trusted_routeros_source():
    results = search_knowledge_base("RouterOS API SSL certificate connection")
    assert results
    assert any(item["source"] == "routeros-operations.md" for item in results)
    assert all(item["content"] for item in results)


@pytest.mark.asyncio
async def test_network_monitor_collects_read_only_snapshot_and_threshold_alerts(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(network_monitor_agent.mikrotik_service, "get_status", lambda: {
        "cpu-load": "92",
        "free-memory": "1024",
        "total-memory": "4096",
        "uptime": "2d 1h",
        "version": "7.18",
    })
    monkeypatch.setattr(network_monitor_agent.mikrotik_service, "get_active_users", lambda: [
        {"user": "test-1"}, {"user": "test-2"}, {"user": "test-3"},
    ])
    monkeypatch.setattr(settings, "NETWORK_CPU_ALERT_THRESHOLD", 80)
    monkeypatch.setattr(settings, "NETWORK_ACTIVE_USERS_ALERT_THRESHOLD", 2)
    monkeypatch.setattr(settings, "NETWORK_ALERT_COOLDOWN_SECONDS", 900)

    async with session_factory() as session:
        snapshot = await network_monitor_agent.collect_network_snapshot(session)
        assert snapshot.cpu_load == 92
        assert snapshot.active_users == 3
        alerts = (await session.execute(
            select(models.NetworkAlert).where(models.NetworkAlert.active.is_(True))
        )).scalars().all()
        codes = {item.code for item in alerts}
        assert {"router_cpu_high", "active_users_high"}.issubset(codes)

    await engine.dispose()


@pytest.mark.asyncio
async def test_diagnostics_collects_aggregate_live_routeros_data_only(monkeypatch):
    monkeypatch.setattr(settings, "MIKROTIK_DEMO_MODE", False)
    monkeypatch.setattr(network_monitor_agent.mikrotik_service, "get_status", lambda: {
        "board-name": "RB-Test",
        "version": "7.18",
        "uptime": "3d",
        "cpu-load": "22",
        "free-memory": "4096",
        "total-memory": "8192",
    })
    monkeypatch.setattr(network_monitor_agent.mikrotik_service, "get_active_users", lambda: [
        {"user": "private-user", "address": "192.0.2.10", "mac-address": "AA:BB:CC:DD:EE:FF"},
        {"user": "private-user-2", "address": "192.0.2.11"},
    ])

    observations = await collect_read_only_observations()
    assert observations["available"] is True
    assert observations["mode"] == "live-read-only"
    assert observations["active_user_count"] == 2
    assert observations["cpu_load_percent"] == "22"
    assert observations["board"] == "RB-Test"
    assert "private-user" not in str(observations)
    assert "192.0.2.10" not in str(observations)


@pytest.mark.asyncio
async def test_diagnostics_does_not_label_demo_values_as_live(monkeypatch):
    monkeypatch.setattr(settings, "MIKROTIK_DEMO_MODE", True)
    observations = await collect_read_only_observations()
    assert observations["available"] is False
    assert observations["mode"] == "demo"
