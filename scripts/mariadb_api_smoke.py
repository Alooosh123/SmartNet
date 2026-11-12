"""Smoke-test the real SmartNet API against an isolated MariaDB deployment.

This exercises persistence, manual-payment validation, subscription activation,
operation approval, and reconciliation. It never executes a MikroTik operation.
"""
from __future__ import annotations

import os
import secrets
import sys

import httpx


BASE_URL = os.environ.get("SMARTNET_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
ADMIN_USERNAME = os.environ.get("DASHBOARD_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
ALLOW_MUTATIONS = os.environ.get("SMARTNET_SMOKE_ALLOW_MUTATIONS") == "YES"
CONFIRMED_TARGET = os.environ.get("SMARTNET_SMOKE_CONFIRM_TARGET") == "isolated-staging-or-ci"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    require(
        ALLOW_MUTATIONS and CONFIRMED_TARGET,
        "This test creates users, writes test payment records, and changes test operation state. "
        "Set SMARTNET_SMOKE_ALLOW_MUTATIONS=YES and "
        "SMARTNET_SMOKE_CONFIRM_TARGET=isolated-staging-or-ci only for an isolated disposable database.",
    )
    require(ADMIN_USERNAME and ADMIN_PASSWORD, "DASHBOARD_USERNAME/PASSWORD must be supplied.")
    suffix = secrets.token_hex(5)
    username = f"mariadb-ci-{suffix}"
    customer_password = f"MariaDB-CI-{secrets.token_urlsafe(18)}"
    transfer_reference = f"SMN-CI-{suffix}"
    duplicate_user = f"mariadb-dup-{suffix}"

    with httpx.Client(base_url=BASE_URL, timeout=20.0) as client:
        # The initial admin is bootstrapped by the application using MariaDB.
        login = client.post(
            "/auth/login",
            data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        require(login.status_code == 200, f"Admin login failed: {login.status_code} {login.text}")
        admin_token = login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Create a real row, verify a manual transfer (amount, currency, reference),
        # then activate the subscription through its separate approval transaction.
        registration_response = client.post(
            "/auth/register",
            json={"username": username, "password": customer_password, "plan": "annual"},
        )
        require(registration_response.status_code == 200, f"Registration failed: {registration_response.text}")
        registration = registration_response.json()
        require(registration["currency"] == "USD" and registration["price"] == 100, "Unexpected annual plan price/currency.")

        invalid_amount = client.post(
            f"/auth/registrations/{registration['registration_id']}/verify-manual",
            headers=admin_headers,
            json={"amount": 99, "currency": "USD", "external_reference": transfer_reference + "-BAD"},
        )
        require(invalid_amount.status_code == 400, "Manual payment accepted a mismatched amount.")

        verified = client.post(
            f"/auth/registrations/{registration['registration_id']}/verify-manual",
            headers=admin_headers,
            json={
                "amount": 100,
                "currency": "USD",
                "external_reference": transfer_reference,
                "notes": "Isolated MariaDB CI acceptance test; no real funds.",
            },
        )
        require(verified.status_code == 200, f"Manual payment verification failed: {verified.status_code} {verified.text}")
        require(verified.json()["paid"] is True and verified.json()["processed"] is False, "Payment verification improperly activated the client.")

        approved = client.post(
            f"/auth/registrations/{registration['registration_id']}/approve",
            headers=admin_headers,
        )
        require(approved.status_code == 200, f"Subscription approval failed: {approved.status_code} {approved.text}")

        status_without_token = client.get(f"/auth/registrations/{registration['registration_id']}/status")
        require(status_without_token.status_code == 401, "Registration status was exposed without its access token.")
        status_with_token = client.get(
            f"/auth/registrations/{registration['registration_id']}/status",
            headers={"X-Registration-Token": registration["registration_token"]},
        )
        require(status_with_token.status_code == 200 and status_with_token.json()["processed"], "Registration state was not persisted.")

        customer_login = client.post(
            "/auth/login",
            data={"username": username, "password": customer_password},
        )
        require(customer_login.status_code == 200, f"Customer login failed: {customer_login.status_code} {customer_login.text}")
        customer_token = customer_login.json()["access_token"]
        customer_headers = {"Authorization": f"Bearer {customer_token}"}
        profile = client.get("/auth/me", headers=customer_headers)
        require(profile.status_code == 200 and profile.json()["plan"] == "annual", "MariaDB customer profile was not persisted.")

        # An annual customer may request a reboot, but the approved operation is
        # rejected in CI. The smoke test never sends a live RouterOS command.
        operation_response = client.post("/mikrotik/reboot", headers=customer_headers)
        require(operation_response.status_code == 202, f"Network operation request failed: {operation_response.status_code} {operation_response.text}")
        operation_id = operation_response.json()["operation_id"]
        rejected = client.post(
            f"/mikrotik/operations/{operation_id}/reject",
            headers=admin_headers,
            json={"note": "CI smoke test — explicitly rejected; no router command executed."},
        )
        require(rejected.status_code == 200 and rejected.json()["status"] == "rejected", "Operation approval state was not persisted.")

        # The same external transfer reference must not be applied to another request.
        duplicate = client.post(
            "/auth/register",
            json={"username": duplicate_user, "password": customer_password, "plan": "monthly"},
        )
        require(duplicate.status_code == 200, f"Second registration failed: {duplicate.text}")
        duplicate_payment = client.post(
            f"/auth/registrations/{duplicate.json()['registration_id']}/verify-manual",
            headers=admin_headers,
            json={"amount": 20, "currency": "USD", "external_reference": transfer_reference},
        )
        require(duplicate_payment.status_code == 409, "Duplicate external payment reference was accepted.")

        reconciliation = client.get("/auth/payments/reconciliation", headers=admin_headers)
        require(reconciliation.status_code == 200, f"Payment reconciliation failed: {reconciliation.text}")
        require(reconciliation.json()["anomaly_count"] == 0, f"Unexpected reconciliation anomalies: {reconciliation.text}")

    print("MariaDB API lifecycle smoke test passed: admin login, registration persistence, manual payment, approval, client login, operation rejection, duplicate reference protection, and reconciliation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"MariaDB API smoke test failed: {exc}", file=sys.stderr)
        raise
