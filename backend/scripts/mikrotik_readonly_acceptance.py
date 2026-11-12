"""Run against an isolated MikroTik test router. No router settings are changed.

Example:
  MIKROTIK_DEMO_MODE=false MIKROTIK_USE_SSL=true python scripts/mikrotik_readonly_acceptance.py
"""
import json
import sys

from config.settings import settings
from services.mikrotik_service import mikrotik_service


def main() -> int:
    if settings.MIKROTIK_DEMO_MODE:
        print("FAIL: MIKROTIK_DEMO_MODE must be false for a real-device acceptance test.")
        return 2
    if not settings.MIKROTIK_USE_SSL or not settings.MIKROTIK_SSL_VERIFY or not settings.MIKROTIK_SSL_VERIFY_HOSTNAME:
        print("FAIL: API-SSL and certificate/hostname verification are required.")
        return 2
    if not settings.MIKROTIK_HOST or not settings.MIKROTIK_USERNAME or not settings.MIKROTIK_PASSWORD:
        print("FAIL: Set router host, dedicated username and password.")
        return 2

    try:
        status = mikrotik_service.get_status()
        profiles = mikrotik_service.get_profiles()
        active_users = mikrotik_service.get_active_users()
    except Exception as exc:
        print(f"FAIL: Read-only RouterOS connection or query failed: {type(exc).__name__}: {exc}")
        return 1

    safe_status = {
        "board-name": status.get("board-name", status.get("board_name")),
        "version": status.get("version"),
        "uptime": status.get("uptime"),
        "cpu-load": status.get("cpu-load", status.get("cpu_load")),
    }
    print(json.dumps({
        "status": "connected",
        "transport": "API-SSL",
        "tls_validation": "enabled",
        "router": safe_status,
        "hotspot_profile_count": len(profiles or []),
        "active_user_count": len(active_users or []),
        "mutations_performed": 0,
    }, ensure_ascii=False, indent=2))
    if not profiles:
        print("WARNING: No Hotspot profiles were returned; card generation is not ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
