"""Idempotent wallet renewal fulfilment tests."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import settings
from database import models
from database.database import Base
from services.wallet_fulfillment import fulfill_wallet_payment_intent
from services.wallet_monitoring import wallet_fingerprint


async def _wallet_fixture(session):
    now = datetime.now(timezone.utc)
    provider = models.WalletProvider(
        code="renewal_wallet",
        display_name="Renewal Wallet",
        package_allowlist='["com.example.renewal"]',
        enabled=True,
        auto_verification_enabled=False,
    )
    device = models.WalletMonitorDevice(
        device_uuid="renewal-device-uuid",
        name="Renewal test phone",
        token_hash="a" * 64,
        status="active",
        notification_access_granted=True,
    )
    client = models.Client(
        username="renewal-client",
        hashed_password="test-hash",
        plan="monthly",
        can_reboot_network=False,
        is_active=True,
        subscription_expires=now + timedelta(days=5),
    )
    session.add_all([provider, device, client])
    await session.flush()

    receiving = models.ReceivingWalletAccount(
        provider_id=provider.id,
        device_id=device.id,
        account_label="Renewal receiving",
        account_fingerprint=wallet_fingerprint("+967777111222"),
        masked_identifier="***1222",
        currency="USD",
        is_active=True,
    )
    payer = models.PayerWalletIdentity(
        client_id=client.id,
        provider_id=provider.id,
        phone_fingerprint=wallet_fingerprint("+967733111222"),
        masked_phone="***1222",
        owner_name="Renewal owner",
        status="active",
        approved_by="test-admin",
        approved_at=now,
    )
    session.add_all([receiving, payer])
    await session.flush()

    intent = models.WalletPaymentIntent(
        client_id=client.id,
        payer_wallet_id=payer.id,
        receiving_wallet_id=receiving.id,
        intent_type="renewal",
        plan="monthly",
        duration_days=30,
        amount=Decimal("20.00"),
        currency="USD",
        reference_token="SN-RENEWAL-INTENT-001",
        status="open",
        expires_at=now + timedelta(hours=2),
    )
    session.add(intent)
    await session.flush()

    transaction = models.WalletTransaction(
        provider_id=provider.id,
        receiving_wallet_id=receiving.id,
        intent_id=intent.id,
        provider_transaction_id="provider-renewal-transaction-001",
        provider_reference="wallet-ref-renewal-001",
        sender_fingerprint=payer.phone_fingerprint,
        recipient_fingerprint=receiving.account_fingerprint,
        amount=Decimal("20.00"),
        currency="USD",
        provider_status="settled",
        verification_status="manually_verified",
        occurred_at=now,
    )
    session.add(transaction)
    await session.commit()
    await session.refresh(client)
    await session.refresh(intent)
    await session.refresh(transaction)
    return now, client, intent, transaction


@pytest.mark.asyncio
async def test_renewal_extends_from_later_of_current_expiry_or_now_and_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "WALLET_IDENTITY_HMAC_SECRET", "fulfillment-test-hmac-" * 3)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        now, client, intent, transaction = await _wallet_fixture(session)
        previous_expiry = client.subscription_expires
        first = await fulfill_wallet_payment_intent(
            session,
            intent_id=intent.id,
            transaction_id=transaction.id,
            actor="finance-admin",
            allow_automatic=False,
            now=now,
        )
        assert first["idempotent_replay"] is False
        refreshed_client = await session.get(models.Client, client.id)
        expected = previous_expiry + timedelta(days=30)
        assert refreshed_client.subscription_expires == expected

        second = await fulfill_wallet_payment_intent(
            session,
            intent_id=intent.id,
            transaction_id=transaction.id,
            actor="finance-admin",
            allow_automatic=False,
            now=now + timedelta(minutes=1),
        )
        assert second["idempotent_replay"] is True
        assert second["fulfillment_id"] == first["fulfillment_id"]
        refreshed_client = await session.get(models.Client, client.id)
        assert refreshed_client.subscription_expires == expected

        rows = await session.execute(select(models.WalletSubscriptionFulfillment))
        assert len(rows.scalars().all()) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_unverified_wallet_transaction_cannot_fulfil_subscription(monkeypatch):
    monkeypatch.setattr(settings, "WALLET_IDENTITY_HMAC_SECRET", "fulfillment-test-hmac-" * 3)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        now, client, intent, transaction = await _wallet_fixture(session)
        transaction.verification_status = "pending_review"
        await session.commit()
        with pytest.raises(ValueError, match="trusted financial verification"):
            await fulfill_wallet_payment_intent(
                session,
                intent_id=intent.id,
                transaction_id=transaction.id,
                actor="wallet-agent",
                allow_automatic=False,
                now=now,
            )
        refreshed_client = await session.get(models.Client, client.id)
        assert refreshed_client.subscription_expires == client.subscription_expires
        rows = await session.execute(select(models.WalletSubscriptionFulfillment))
        assert rows.scalars().all() == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_transaction_sender_fingerprint_must_match_approved_wallet(monkeypatch):
    monkeypatch.setattr(settings, "WALLET_IDENTITY_HMAC_SECRET", "fulfillment-test-hmac-" * 3)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        now, client, intent, transaction = await _wallet_fixture(session)
        transaction.sender_fingerprint = "f" * 64
        await session.commit()
        with pytest.raises(ValueError, match="sender"):
            await fulfill_wallet_payment_intent(
                session,
                intent_id=intent.id,
                transaction_id=transaction.id,
                actor="finance-admin",
                allow_automatic=False,
                now=now,
            )
        rows = await session.execute(select(models.WalletSubscriptionFulfillment))
        assert rows.scalars().all() == []

    await engine.dispose()
