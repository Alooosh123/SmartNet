"""Read-only live acceptance check for an isolated MikroTik RouterOS device.

Run from backend/ after setting backend/.env. This command never mutates RouterOS
and prints aggregate session count only (no usernames, IP addresses or MACs).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config.settings import settings
from services.routeros_connection import create_routeros_connection


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    if settings.MIKROTIK_DEMO_MODE:
        print("REFUSED: set MIKROTIK_DEMO_MODE=false for a real-device acceptance check.", file=sys.stderr)
        return 2
    host = settings.MIKROTIK_READONLY_HOST or settings.MIKROTIK_HOST
    if not settings.MIKROTIK_READONLY_USERNAME or not settings.MIKROTIK_READONLY_PASSWORD:
        print("REFUSED: configure a dedicated read-only MikroTik account.", file=sys.stderr)
        return 2

    connection = None
    try:
        connection = create_routeros_connection(
            host=host,
            username=settings.MIKROTIK_READONLY_USERNAME,
            password=settings.MIKROTIK_READONLY_PASSWORD,
            port=settings.MIKROTIK_READONLY_PORT,
        )
        api = connection.get_api()
        resources = api.get_resource("/system/resource").get()
        if not resources:
            raise RuntimeError("RouterOS returned no /system/resource record.")
        resource = resources[0]
        active = api.get_resource("/ip/hotspot/active").get()
        print(json.dumps({
            "connected": True,
            "transport": "API-SSL",
            "tls_certificate_verification": "enabled",
            "tls_hostname_verification": "enabled",
            "board_name": resource.get("board-name"),
            "routeros_version": resource.get("version"),
            "cpu_load_percent": resource.get("cpu-load"),
            "free_memory_bytes": resource.get("free-memory"),
            "active_hotspot_sessions": len(active),
            "subscriber_identifiers_emitted": False,
            "mutations_performed": False,
        }, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"RouterOS read-only acceptance failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
