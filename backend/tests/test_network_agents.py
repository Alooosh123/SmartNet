import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.database import Base
from database.models import NetworkObservation
from config.settings import settings
from services import network_observer
from services.network_diagnostic_agent import diagnose_latest_network


@pytest.mark.asyncio
async def test_network_observer_persists_aggregate_read_only_snapshot(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(network_observer, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(network_observer.mikrotik_readonly_service, "get_status", lambda: {
        "board-name": "Test Router",
        "version": "7.20",
        "cpu-load": "91",
        "free-memory": "10485760",
    })
    monkeypatch.setattr(network_observer.mikrotik_readonly_service, "get_active_users", lambda: [
        {"user": "private-user", "address": "192.0.2.10", "mac-address": "00:00:00:00:00:01"},
        {"user": "another-user", "address": "192.0.2.11", "mac-address": "00:00:00:00:00:02"},
    ])
    monkeypatch.setattr(settings, "NETWORK_ALERT_CPU_THRESHOLD", 85)
    monkeypatch.setattr(settings, "NETWORK_ALERT_FREE_MEMORY_MB", 32)
    monkeypatch.setattr(settings, "NETWORK_OBSERVER_HISTORY_LIMIT", 25)

    # Dedicated observer adapter exposes no RouterOS mutation methods.
    assert not hasattr(network_observer.mikrotik_readonly_service, "reboot_router")
    assert not hasattr(network_observer.mikrotik_readonly_service, "disconnect_user")

    snapshot = await network_observer.collect_network_observation()
    assert snapshot["status"] == "warning"
    assert snapshot["cpu_load"] == 91
    assert snapshot["free_memory_mb"] == 10
    assert snapshot["active_users_count"] == 2
    assert "private-user" not in str(snapshot)
    assert "00:00:00:00:00:01" not in str(snapshot)

    async with session_factory() as session:
        rows = (await session.execute(select(NetworkObservation))).scalars().all()
        assert len(rows) == 1
        assert rows[0].active_users_count == 2
        assert rows[0].warning

        monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
        diagnosis = await diagnose_latest_network(session, "لماذا الشبكة بطيئة؟")
        assert diagnosis["read_only"] is True
        assert diagnosis["observation"]["cpu_load"] == 91
        assert diagnosis["knowledge_base"] == "curated-mikrotik-operations"
        assert diagnosis["sources"]

    await engine.dispose()
