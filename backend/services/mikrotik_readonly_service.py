"""Dedicated read-only RouterOS adapter for the Network Observer.

This module intentionally exposes no mutation methods. Production uses a
separate RouterOS account with read-only policy, not the operational account.
"""
from config.settings import settings

from services.mikrotik_service import mikrotik_service
from services.routeros_connection import create_routeros_connection


class MikroTikReadOnlyService:
    def _get_api(self):
        if settings.MIKROTIK_DEMO_MODE:
            return None
        host = settings.MIKROTIK_READONLY_HOST or settings.MIKROTIK_HOST
        return create_routeros_connection(
            host=host,
            username=settings.MIKROTIK_READONLY_USERNAME or "",
            password=settings.MIKROTIK_READONLY_PASSWORD or "",
            port=settings.MIKROTIK_READONLY_PORT,
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
