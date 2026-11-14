"""Wallet monitoring API tests.

The suite uses an isolated SQLite database and never contacts a real wallet app.
It verifies device authentication, registration-token ownership, idempotent event
intake, masked identity handling and the fail-closed adapter state.
"""
import asyncio
import hashlib
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.dependencies import get_db
from app import app
from config.settings import settings
from database import models
from database.database import Base
from services.auth_service import auth_service
from services.wallet_monitoring import (
    ParsedWalletTransfer,
    mask_wallet_identifier,
    normalize_wallet_identifier,
    register_notification_parser,
    wallet_fingerprint,
)


def test_normalize_arabic_wallet_digits_and_mask():
    value = normalize_wallet_identifier("٠٥٠-١٢٣ ٤٥٦٧")
    assert value == "0501234567"
    assert mask_wallet_identifier(value) == "***4567"


def test_wallet_fingerprint_uses_keyed_digest(monkeypatch):
    monkeypatch.setattr(settings, "WALLET_IDENTITY_HMAC_SECRET", "h" * 48)
    first = wallet_fingerprint("+967 777 123 456")
    second = wallet_fingerprint("+967777123456")
    assert first == second
    assert len(first) == 64
    assert first != hashlib.sha256(b"+967777123456").hexdigest()


@pytest.fixture
def wallet_api(tmp_path, monkeypatch):
    database_path = tmp_path / "wallet-monitor.db"
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    registration_token = "registration-token-for-wallet-tests"
    registration_id_holder = {}

    async def initialize_database():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(models.Admin(
                username="wallet-admin",
                hashed_password=auth_service.get_password_hash("Wallet-admin-password-2026!"),
                is_active=True,
            ))
            registration = models.RegistrationRequest(
                username="wallet-new-owner",
                hashed_password=auth_service.get_password_hash("Wallet-customer-password-2026!"),
                plan="monthly",
                price=20,
                currency="USD",
                registration_token_hash=hashlib.sha256(registration_token.encode()).hexdigest(),
                paid=False,
                processed=False,
            )
            session.add(registration)
            await session.commit()
            await session.refresh(registration)
            registration_id_holder["id"] = registration.id

    asyncio.run(initialize_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER_MODE", "manual")
    monkeypatch.setattr(settings, "PAYMENT_DEMO_MODE", False)
    monkeypatch.setattr(settings, "MIKROTIK_DEMO_MODE", True)
    monkeypatch.setattr(settings, "NETWORK_OBSERVER_ENABLED", False)
    monkeypatch.setattr(settings, "WALLET_MONITORING_ENABLED", True)
    monkeypatch.setattr(settings, "WALLET_AUTO_ACTIVATION_ENABLED", False)
    monkeypatch.setattr(settings, "WALLET_IDENTITY_HMAC_SECRET", "wallet-test-hmac-secret-" * 3)
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "registration_id": registration_id_holder["id"],
            "registration_token": registration_token,
        }
    finally:
        client.close()
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def test_wallet_device_registration_identity_and_event_intake(wallet_api):
    client = wallet_api["client"]
    registration_id = wallet_api["registration_id"]
    registration_token = wallet_api["registration_token"]

    login = client.post(
        "/auth/login",
        data={"username": "wallet-admin", "password": "Wallet-admin-password-2026!"},
    )
    assert login.status_code == 200, login.text
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    provider = client.post(
        "/api/v1/wallet-monitor/admin/providers",
        headers=admin_headers,
        json={
            "code": "test_wallet",
            "display_name": "Test Wallet",
            "package_names": ["com.example.wallet"],
        },
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["id"]
    assert provider.json()["auto_verification_enabled"] is False

    device_response = client.post(
        "/api/v1/wallet-monitor/admin/devices",
        headers=admin_headers,
        json={"name": "Dedicated wallet phone"},
    )
    assert device_response.status_code == 200, device_response.text
    device_token = device_response.json()["device_token"]
    device_headers = {"Authorization": f"Bearer {device_token}"}

    receiver = client.post(
        "/api/v1/wallet-monitor/admin/receiving-wallets",
        headers=admin_headers,
        json={
            "provider_id": provider_id,
            "device_id": device_response.json()["id"],
            "account_label": "Platform USD wallet",
            "account_identifier": "+967 777 000 111",
            "currency": "USD",
        },
    )
    assert receiver.status_code == 200, receiver.text
    receiver_id = receiver.json()["id"]
    assert receiver.json()["masked_identifier"] == "***0111"

    payer = client.post(
        f"/api/v1/wallet-monitor/registrations/{registration_id}/payer-wallets",
        headers={"X-Registration-Token": registration_token},
        json={
            "provider_id": provider_id,
            "wallet_identifier": "+967 733 123 456",
            "owner_name": "First Wallet Owner",
        },
    )
    assert payer.status_code == 200, payer.text
    payer_id = payer.json()["id"]
    assert payer.json()["status"] == "pending_approval"
    assert "phone_fingerprint" not in payer.json()
    assert "wallet_identifier" not in payer.json()

    intent = client.post(
        f"/api/v1/wallet-monitor/registrations/{registration_id}/payment-intents",
        headers={"X-Registration-Token": registration_token},
        json={"payer_wallet_id": payer_id, "receiving_wallet_id": receiver_id},
    )
    assert intent.status_code == 200, intent.text
    assert intent.json()["amount"] == "20.00"
    assert intent.json()["currency"] == "USD"
    assert intent.json()["automatic_activation"] is False

    heartbeat = client.post(
        "/api/v1/wallet-monitor/device/heartbeat",
        headers=device_headers,
        json={"app_version": "0.1.0", "notification_access_granted": True},
    )
    assert heartbeat.status_code == 200, heartbeat.text
    assert heartbeat.json()["notification_access_granted"] is True

    register_notification_parser(
        "test_wallet",
        lambda title, body: ParsedWalletTransfer(
            provider_transaction_id="test-provider-transaction-001",
            provider_reference="test-provider-reference-001",
            sender_identifier="+967 733 123 456",
            recipient_identifier="+967 777 000 111",
            amount=Decimal("20.00"),
            currency="USD",
            provider_status="settled",
            occurred_at=datetime.now(timezone.utc),
        ),
    )

    event_payload = {
        "event_uuid": "5ca1c8c1-7db2-4c44-9d60-3e7c6b86db44",
        "package_name": "com.example.wallet",
        "title": "Transfer received",
        "body": "This is test notification content and must not be stored.",
        "notification_posted_at": datetime.now(timezone.utc).isoformat(),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    received = client.post(
        "/api/v1/wallet-monitor/device/events",
        headers=device_headers,
        json=event_payload,
    )
    assert received.status_code == 200, received.text
    assert received.json()["parse_status"] == "candidate_for_review"
    assert received.json()["automatic_activation"] is False

    duplicate = client.post(
        "/api/v1/wallet-monitor/device/events",
        headers=device_headers,
        json=event_payload,
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["duplicate"] is True

    event_list = client.get("/api/v1/wallet-monitor/admin/events", headers=admin_headers)
    assert event_list.status_code == 200, event_list.text
    assert len(event_list.json()) == 1
    event_record = event_list.json()[0]
    assert event_record["payload_sha256"]
    assert "body" not in event_record
    assert "title" not in event_record

    transactions = client.get("/api/v1/wallet-monitor/admin/transactions", headers=admin_headers)
    assert transactions.status_code == 200, transactions.text
    assert len(transactions.json()) == 1
    transaction = transactions.json()[0]
    assert transaction["verification_status"] == "pending_review"

    first_verification = client.post(
        f"/api/v1/wallet-monitor/admin/transactions/{transaction['id']}/verify",
        headers=admin_headers,
        json={
            "observed_provider_identifier": "test-provider-transaction-001",
            "amount": "20.00",
            "currency": "USD",
            "confirmed_in_wallet_app": True,
            "note": "Verified first transfer directly inside the test wallet app.",
        },
    )
    # The payment is recorded as financially verified, but fulfilment is blocked
    # while the payer identity is still pending first-transfer approval.
    assert first_verification.status_code == 409, first_verification.text

    identity_approval = client.post(
        f"/api/v1/wallet-monitor/admin/payer-wallets/{payer_id}/approve",
        headers=admin_headers,
    )
    assert identity_approval.status_code == 200, identity_approval.text
    assert identity_approval.json()["status"] == "active"
    assert identity_approval.json()["first_transaction_id"] == transaction["id"]
    assert identity_approval.json()["client_id"]
    assert identity_approval.json()["fulfillment_id"]

    registrations = client.get("/auth/registrations", headers=admin_headers)
    registered = next(item for item in registrations.json() if item["id"] == registration_id)
    assert registered["paid"] is True
    assert registered["processed"] is True

    assert client.post(
        "/api/v1/wallet-monitor/device/heartbeat",
        json={"app_version": "0.1.0", "notification_access_granted": True},
    ).status_code == 401


def test_wallet_monitoring_disabled_and_auto_activation_rejected(wallet_api, monkeypatch):
    from pydantic import ValidationError
    from config.settings import Settings

    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            WALLET_AUTO_ACTIVATION_ENABLED=True,
        )

    client = wallet_api["client"]
    monkeypatch.setattr(settings, "WALLET_MONITORING_ENABLED", False)
    response = client.post(
        "/api/v1/wallet-monitor/device/heartbeat",
        headers={"Authorization": "Bearer " + "x" * 48},
        json={"app_version": "0.1.0", "notification_access_granted": True},
    )
    assert response.status_code == 503
