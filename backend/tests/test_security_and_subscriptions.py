from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.database import Base
from database import models
from services.auth_service import auth_service
from config.settings import Settings
from services.subscription_agent import process_pending_registrations


def test_password_hash_and_policy():
    with pytest.raises(ValueError):
        auth_service.get_password_hash("short")
    hashed = auth_service.get_password_hash("A-long-local-test-password-2026!")
    assert auth_service.verify_password("A-long-local-test-password-2026!", hashed)
    assert not auth_service.verify_password("wrong-password", hashed)


def _production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "s" * 48,
        "PAYMENT_WEBHOOK_SECRET": "w" * 48,
        "DASHBOARD_USERNAME": "smartnet-owner",
        "DASHBOARD_PASSWORD": "admin-strong-password-2026!",
        "PAYMENT_DEMO_MODE": False,
        "MIKROTIK_DEMO_MODE": False,
        "MIKROTIK_PASSWORD": "router-strong-password",
        "DATABASE_URL": "mysql+asyncmy://smartnet_app:runtime-secret@127.0.0.1:3306/smartnet",
        "MIGRATION_DATABASE_URL": "mysql+asyncmy://smartnet_migrator:migration-secret@127.0.0.1:3306/smartnet",
        "PAYMENT_PROVIDER_MODE": "manual",
        "POSTGRES_PASSWORD": "postgres-strong-password-2026",
        "CORS_ORIGINS": ["https://smartnet.example"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_accept_realistic_manual_payment_configuration():
    settings = _production_settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.PAYMENT_PROVIDER_MODE == "manual"


def test_production_settings_reject_shared_mariadb_runtime_and_migration_user():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _production_settings(
            MIGRATION_DATABASE_URL="mysql+asyncmy://smartnet_app:runtime-secret@127.0.0.1:3306/smartnet"
        )


@pytest.mark.asyncio
async def test_paid_registration_is_not_auto_activated():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        registration = models.RegistrationRequest(
            username="review-only-user",
            hashed_password=auth_service.get_password_hash("Another-long-password-2026!"),
            plan="monthly",
            price=20,
            paid=True,
            payment_ref="provider-transaction-001",
            processed=False,
            created_at=datetime.now(timezone.utc),
        )
        session.add(registration)
        await session.commit()

        processed = await process_pending_registrations(session, force_now=True)
        assert processed == 0

        refreshed = await session.get(models.RegistrationRequest, registration.id)
        clients = await session.execute(
            select(models.Client).where(models.Client.username == "review-only-user")
        )
        assert refreshed is not None
        assert refreshed.processed is False
        assert clients.scalars().first() is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_does_not_mark_registration_as_paid():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        registration = models.RegistrationRequest(
            username="receipt-only-user",
            hashed_password=auth_service.get_password_hash("Receipt-only-password-2026!"),
            plan="monthly",
            price=20,
            paid=False,
            receipt_image="uploads/receipts/receipt.png",
            processed=False,
        )
        session.add(registration)
        await session.commit()
        await process_pending_registrations(session, force_now=True)
        refreshed = await session.get(models.RegistrationRequest, registration.id)
        assert refreshed is not None
        assert refreshed.paid is False
        assert refreshed.processed is False
    await engine.dispose()
