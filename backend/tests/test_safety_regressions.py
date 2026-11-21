import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from database import models
from config.settings import settings
from services.subscription_agent import process_pending_registrations
from services.mikrotik_api import MikroTikClient
from services.mikrotik_service import MikroTikService


class FakeScalars:
    def __init__(self, rows):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def scalars(self):
        return FakeScalars(self._rows)


class FakeAsyncSession:
    """Minimal async SQLAlchemy session fake for subscription-agent safety tests."""

    def __init__(self, registrations, existing_receipt_audit=False):
        self.registrations = registrations
        self.existing_receipt_audit = existing_receipt_audit
        self.execute_count = 0
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count == 1:
            # is_bot_enabled(): no explicit setting means enabled by default.
            return FakeResult()
        if self.execute_count == 2:
            return FakeResult(self.registrations)
        if self.existing_receipt_audit:
            return FakeResult([object()])
        return FakeResult()

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True


def make_registration(*, paid=False, receipt_image=None):
    return SimpleNamespace(
        id=123,
        username="safety_test_user",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        plan="monthly",
        paid=paid,
        receipt_image=receipt_image,
        processed=False,
        hashed_password="not-used-by-this-test",
    )


class SubscriptionAgentSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_receipt_image_does_not_confirm_payment_or_activate_account(self):
        registration = make_registration(receipt_image="/uploads/receipts/test.jpg")
        db = FakeAsyncSession([registration])

        notices_sent = await process_pending_registrations(db, force_now=True)

        self.assertEqual(notices_sent, 1)
        self.assertFalse(registration.paid)
        self.assertFalse(registration.processed)
        self.assertFalse(any(isinstance(item, models.Client) for item in db.added))
        self.assertTrue(any(
            isinstance(item, models.AuditLog)
            and item.action == "bot_receipt_pending_review"
            for item in db.added
        ))
        self.assertTrue(db.committed)

    async def test_verified_payment_still_requires_manual_activation_approval(self):
        registration = make_registration(paid=True)
        db = FakeAsyncSession([registration])

        notices_sent = await process_pending_registrations(db, force_now=True)

        self.assertEqual(notices_sent, 0)
        self.assertTrue(registration.paid)
        self.assertFalse(registration.processed)
        self.assertFalse(any(isinstance(item, models.Client) for item in db.added))
        self.assertFalse(db.committed)

    async def test_receipt_review_notice_is_not_duplicated(self):
        registration = make_registration(receipt_image="/uploads/receipts/test.jpg")
        db = FakeAsyncSession([registration], existing_receipt_audit=True)

        notices_sent = await process_pending_registrations(db, force_now=True)

        self.assertEqual(notices_sent, 0)
        self.assertEqual(db.added, [])
        self.assertFalse(registration.paid)
        self.assertFalse(registration.processed)


class MikroTikFailClosedTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_real_mode_fails_if_routeros_package_is_missing(self):
        client = MikroTikClient(demo_mode=False)
        with patch("services.mikrotik_api.ROUTEROS_AVAILABLE", False):
            with self.assertRaisesRegex(RuntimeError, "routeros_api is required"):
                await client.get_status()

    async def test_client_real_mode_does_not_fallback_after_connection_error(self):
        client = MikroTikClient(demo_mode=False)
        with patch("services.mikrotik_api.ROUTEROS_AVAILABLE", True):
            with patch.object(client, "_get_connection", side_effect=OSError("router offline")):
                with self.assertRaisesRegex(RuntimeError, "Real MikroTik status unavailable"):
                    await client.get_status()

    def test_service_real_mode_fails_if_routeros_package_is_missing(self):
        service = MikroTikService()
        with patch("services.mikrotik_service.ROUTEROS_AVAILABLE", False):
            with patch.object(settings, "MIKROTIK_DEMO_MODE", False):
                with self.assertRaisesRegex(RuntimeError, "routeros_api is required"):
                    service.get_status()


if __name__ == "__main__":
    unittest.main()
