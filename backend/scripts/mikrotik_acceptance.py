"""Read-only-by-default RouterOS acceptance test.

Run from backend/. The optional write probe is for an isolated test router only:
it creates one disabled test hotspot user, verifies it, and removes it.
"""
import argparse
import json
import os
import secrets
import string

from config.settings import settings


def main():
    parser = argparse.ArgumentParser(description="SmartNet MikroTik acceptance checks")
    parser.add_argument("--write-probe", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--profile", default=os.getenv("MIKROTIK_TEST_PROFILE", ""))
    args = parser.parse_args()

    if settings.MIKROTIK_DEMO_MODE:
        raise SystemExit("Refusing live acceptance: set MIKROTIK_DEMO_MODE=false.")
    if args.write_probe and not args.confirm_write:
        raise SystemExit("Write probe requires --write-probe and --confirm-write.")
    if args.write_probe and not args.profile:
        raise SystemExit("Set MIKROTIK_TEST_PROFILE to an existing isolated test profile.")

    import routeros_api

    connection = routeros_api.RouterOsApiPool(
        settings.MIKROTIK_HOST,
        username=settings.MIKROTIK_USERNAME,
        password=settings.MIKROTIK_PASSWORD,
        port=settings.MIKROTIK_PORT,
        use_ssl=settings.MIKROTIK_USE_SSL,
        ssl_verify=settings.MIKROTIK_USE_SSL,
        ssl_verify_hostname=settings.MIKROTIK_USE_SSL,
        plaintext_login=not settings.MIKROTIK_USE_SSL,
    )
    probe_name = "snprobe" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    try:
        api = connection.get_api()
        resources = api.get_resource("/system/resource").get()
        identity = api.get_resource("/system/identity").get()
        profiles = api.get_resource("/ip/hotspot/user/profile").get()
        active = api.get_resource("/ip/hotspot/active").get()
        result = {
            "connection": "success",
            "identity": identity[0].get("name") if identity else None,
            "router_version": resources[0].get("version") if resources else None,
            "router_board": resources[0].get("board-name") if resources else None,
            "hotspot_profiles": [item.get("name") for item in profiles],
            "active_sessions": len(active),
            "write_probe": "not_run",
        }

        if args.write_probe:
            users = api.get_resource("/ip/hotspot/user")
            users.add(
                name=probe_name,
                password="".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(20)),
                profile=args.profile,
                disabled="yes",
            )
            try:
                found = users.get(name=probe_name)
                if not found:
                    raise RuntimeError("Probe user was not visible after creation.")
                result["write_probe"] = "create_verified"
            finally:
                found = users.get(name=probe_name)
                if found:
                    users.remove(id=found[0].get(".id"))
                result["write_probe_cleanup"] = "attempted"
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        connection.disconnect()


if __name__ == "__main__":
    main()
