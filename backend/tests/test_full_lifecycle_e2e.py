"""End-to-end API lifecycle test using an isolated database and a simulated MikroTik.

This is a software acceptance test. It does not contact a real router or payment
provider; it exercises the real FastAPI routes, SQLAlchemy models, file uploads,
PDF generator, authorization dependencies and subscriber workflow.
"""
import asyncio
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import app
from config.settings import settings
from database.database import Base, get_db
from database import models
from services.auth_service import auth_service


@pytest.fixture
def smartnet_e2e(tmp_path, monkeypatch):
    database_path = tmp_path / "smartnet-e2e.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
        poolclass=NullPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def initialize_database():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(models.Admin(
                username="e2e-admin",
                hashed_password=auth_service.get_password_hash("E2E-admin-password-2026!"),
                is_active=True,
            ))
            await session.commit()

    asyncio.run(initialize_database())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER_MODE", "manual")
    monkeypatch.setattr(settings, "PAYMENT_DEMO_MODE", False)
    monkeypatch.setattr(settings, "MIKROTIK_DEMO_MODE", True)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        yield {
            "client": client,
        }

    app.dependency_overrides.clear()

    async def collect_files():
        async with session_factory() as session:
            from sqlalchemy import select
            batches = (await session.execute(select(models.CardBatch))).scalars().all()
            registrations = (await session.execute(select(models.RegistrationRequest))).scalars().all()
            return [b.pdf_path for b in batches if b.pdf_path], [r.receipt_image for r in registrations if r.receipt_image]

    pdf_paths, receipt_paths = asyncio.run(collect_files())
    for stored_path in pdf_paths:
        Path(stored_path).unlink(missing_ok=True)
    backend_root = Path(__file__).resolve().parents[1]
    for stored_path in receipt_paths:
        (backend_root / stored_path).unlink(missing_ok=True)
    asyncio.run(engine.dispose())


def _login(client, username, password):
    response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _register(client, username, password, plan):
    response = client.post(
        "/auth/register",
        json={"username": username, "password": password, "plan": plan},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["registration_id"]
    assert payload["registration_token"]
    assert payload["payment_demo_available"] is False
    return payload


def _approve_manually(client, admin_headers, registration):
    response = client.post(
        f"/auth/registrations/{registration['registration_id']}/verify-manual",
        headers=admin_headers,
        json={
            "amount": registration["price"],
            "currency": registration.get("currency", "USD"),
            "external_reference": f"E2E-TRANSFER-{registration['registration_id']}",
            "notes": "Controlled isolated end-to-end test transfer",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["paid"] is True
    response = client.post(
        f"/auth/registrations/{registration['registration_id']}/approve",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"]


def test_full_customer_registration_to_payment_approval_chat_and_card_pdf(smartnet_e2e):
    client = smartnet_e2e["client"]

    # Administrator authentication and registration queue access.
    admin_token = _login(client, "e2e-admin", "E2E-admin-password-2026!")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/auth/registrations", headers=admin_headers).status_code == 200

    # Customer creates an annual subscription request and uploads a real PNG receipt.
    registration = _register(
        client,
        "e2e-annual-customer",
        "E2E-customer-password-2026!",
        "annual",
    )
    image_bytes = BytesIO()
    Image.new("RGB", (12, 12), (24, 120, 90)).save(image_bytes, format="PNG")
    upload = client.post(
        f"/auth/registrations/{registration['registration_id']}/receipt",
        headers={"X-Registration-Token": registration["registration_token"]},
        files={"file": ("receipt.png", image_bytes.getvalue(), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["receipt_uploaded"] is True
    assert upload.json()["paid"] is False
    assert upload.json()["processed"] is False

    # Only the owner token can inspect request state; a receipt alone is not payment.
    status_headers = {"X-Registration-Token": registration["registration_token"]}
    status_response = client.get(
        f"/auth/registrations/{registration['registration_id']}/status",
        headers=status_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["receipt_uploaded"] is True
    assert status_response.json()["paid"] is False
    assert client.get(
        f"/auth/registrations/{registration['registration_id']}/status"
    ).status_code == 401

    # The authenticated administrator can privately view the receipt, verify funds,
    # then activate the account as a separate auditable operation.
    admin_queue = client.get("/auth/registrations", headers=admin_headers)
    assert admin_queue.status_code == 200
    receipt_item = next(item for item in admin_queue.json() if item["id"] == registration["registration_id"])
    assert receipt_item["receipt_image"]
    receipt_response = client.get(receipt_item["receipt_image"], headers=admin_headers)
    assert receipt_response.status_code == 200
    assert receipt_response.content.startswith(b"\x89PNG")

    # Wrong amount must fail closed; valid manual verification is a separate step.
    wrong_amount = client.post(
        f"/auth/registrations/{registration['registration_id']}/verify-manual",
        headers=admin_headers,
        json={"amount": registration["price"] + 1, "currency": "USD", "external_reference": "E2E-WRONG-AMOUNT"},
    )
    assert wrong_amount.status_code == 400

    _approve_manually(client, admin_headers, registration)

    approved_status = client.get(
        f"/auth/registrations/{registration['registration_id']}/status",
        headers=status_headers,
    )
    assert approved_status.status_code == 200
    assert approved_status.json()["processed"] is True

    # Customer signs in and sees the real approved subscription and permissions.
    customer_token = _login(client, "e2e-annual-customer", "E2E-customer-password-2026!")
    customer_headers = {"Authorization": f"Bearer {customer_token}"}
    profile = client.get("/auth/me", headers=customer_headers)
    assert profile.status_code == 200
    assert profile.json()["plan"] == "annual"
    assert profile.json()["can_manage_cards"] is True
    assert profile.json()["can_reboot_network"] is True

    # Customer can use the support chat; no live network facts are fabricated.
    chat = client.post(
        "/client/chat",
        headers=customer_headers,
        json={"message": "ما مميزات باقتي؟"},
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["reply"]
    history = client.get(
        "/client/chat",
        headers=customer_headers,
        params={"username": "e2e-annual-customer"},
    )
    assert history.status_code == 200
    assert len(history.json()) >= 2

    # Reboot requests in chat must not operate the router. A separate, confirmed UI
    # action is required and the backend permission is still checked.
    reboot_chat = client.post(
        "/client/chat",
        headers=customer_headers,
        json={"message": "إعادة تشغيل الراوتر"},
    )
    assert reboot_chat.status_code == 200
    assert reboot_chat.json()["model"] == "smartnet-safe-action-guidance"

    # Generate a real PDF against the deterministic demo RouterOS adapter.
    generated = client.post(
        "/cards/generate",
        headers=customer_headers,
        json={"count": 3, "profile": "1 Day", "length": 8, "hide_password": False},
    )
    assert generated.status_code == 200, generated.text
    batch = generated.json()
    assert batch["count"] == 3

    batches = client.get("/cards/batches", headers=customer_headers)
    assert batches.status_code == 200
    assert any(item["id"] == batch["id"] for item in batches.json())
    assert all("pdf_path" not in item for item in batches.json())

    pdf = client.get(f"/cards/{batch['id']}/pdf", headers=customer_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    # A second paid subscriber may generate cards, but cannot list or download the
    # first subscriber's batch (IDOR regression check).
    second = _register(
        client,
        "e2e-semi-customer",
        "E2E-second-password-2026!",
        "semi_annual",
    )
    duplicate_reference = client.post(
        f"/auth/registrations/{second['registration_id']}/verify-manual",
        headers=admin_headers,
        json={"amount": second["price"], "currency": "USD", "external_reference": f"E2E-TRANSFER-{registration['registration_id']}"},
    )
    assert duplicate_reference.status_code == 409
    _approve_manually(client, admin_headers, second)
    second_token = _login(client, "e2e-semi-customer", "E2E-second-password-2026!")
    second_headers = {"Authorization": f"Bearer {second_token}"}
    second_batches = client.get("/cards/batches", headers=second_headers)
    assert second_batches.status_code == 200
    assert all(item["id"] != batch["id"] for item in second_batches.json())
    cross_account_pdf = client.get(f"/cards/{batch['id']}/pdf", headers=second_headers)
    assert cross_account_pdf.status_code == 404

    # Monthly clients cannot access card management even with a valid token.
    monthly = _register(
        client,
        "e2e-monthly-customer",
        "E2E-monthly-password-2026!",
        "monthly",
    )
    _approve_manually(client, admin_headers, monthly)
    monthly_token = _login(client, "e2e-monthly-customer", "E2E-monthly-password-2026!")
    monthly_headers = {"Authorization": f"Bearer {monthly_token}"}
    assert client.get("/cards/batches", headers=monthly_headers).status_code == 403

    # A customer may request a protected network operation but cannot approve
    # or execute it; an administrator must review and execute it separately.
    reboot_request = client.post("/mikrotik/reboot", headers=customer_headers)
    assert reboot_request.status_code == 202
    operation_id = reboot_request.json()["operation_id"]
    assert reboot_request.json()["status"] == "pending"
    unapproved_execute = client.post(f"/mikrotik/operations/{operation_id}/execute", headers=admin_headers)
    assert unapproved_execute.status_code == 409
    approved = client.post(f"/mikrotik/operations/{operation_id}/approve", headers=admin_headers, json={"note": "E2E approval"})
    assert approved.status_code == 200
    executed = client.post(f"/mikrotik/operations/{operation_id}/execute", headers=admin_headers)
    assert executed.status_code == 200
    assert executed.json()["status"] == "executed"
    duplicate_execute = client.post(f"/mikrotik/operations/{operation_id}/execute", headers=admin_headers)
    assert duplicate_execute.status_code == 409

    # Monthly users may not request reboot. Admin self-approval is prohibited
    # for high-impact reboot requests.
    forbidden_reboot = client.post("/mikrotik/reboot", headers=monthly_headers)
    assert forbidden_reboot.status_code == 403
    admin_reboot_request = client.post("/mikrotik/reboot", headers=admin_headers)
    assert admin_reboot_request.status_code == 202
    admin_self_approval = client.post(
        f"/mikrotik/operations/{admin_reboot_request.json()['operation_id']}/approve",
        headers=admin_headers,
        json={"note": "Must be rejected"},
    )
    assert admin_self_approval.status_code == 409

    reconciliation = client.get("/auth/payments/reconciliation", headers=admin_headers)
    assert reconciliation.status_code == 200
    assert reconciliation.json()["anomaly_count"] == 0
