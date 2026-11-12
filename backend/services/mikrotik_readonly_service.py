"""Dedicated read-only RouterOS adapter for the Network Observer.

This module intentionally exposes no mutation methods. Production uses a
separate RouterOS account with read-only policy, not the operational account.
"""
from config.settings import settings

try:
    import routeros_api
except ImportError:  # pragma: no cover - installation validation catches this
    routeros_api = None

from services.mikrotik_service import mikrotik_service


class MikroTikReadOnlyService:
    def _get_api(self):
        if settings.MIKROTIK_DEMO_MODE:
            return None
        if routeros_api is None:
            raise RuntimeError("routeros_api is not installed.")
        host = settings.MIKROTIK_READONLY_HOST or settings.MIKROTIK_HOST
        if not host or not settings.MIKROTIK_READONLY_USERNAME or not settings.MIKROTIK_READONLY_PASSWORD:
            raise RuntimeError("Read-only MikroTik API credentials are not configured.")
        return routeros_api.RouterOsApiPool(
            host,
            username=settings.MIKROTIK_READONLY_USERNAME,
            password=settings.MIKROTIK_READONLY_PASSWORD,
            port=settings.MIKROTIK_READONLY_PORT,
            plaintext_login=True,
        )

    def get_status(self):
        if settings.MIKROTIK_DEMO_MODE:
            return mikrotik_service.get_status()
        connection = self._get_api()
        try:
            api = connection.get_api()
            records = api.get_resource("/system/resource").get()
            return records[0] if records else {}
        finally:
            connection.disconnect()

    def get_active_users(self):
        if settings.MIKROTIK_DEMO_MODE:
            return mikrotik_service.get_active_users()
        connection = self._get_api()
        try:
            api = connection.get_api()
            return api.get_resource("/ip/hotspot/active").get()
        finally:
            connection.disconnect()


mikrotik_readonly_service = MikroTikReadOnlyService()
