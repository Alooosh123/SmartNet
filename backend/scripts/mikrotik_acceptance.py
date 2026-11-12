"""Read-only-by-default RouterOS acceptance test.

Default checks use a dedicated read-only service account. The optional write
probe uses the separate control account and is only for an isolated test router.
"""
import argparse
import json
import os
import secrets
import string

from config.settings import settings


def make_connection(username: str, password: str):
    import routeros_api
    return routeros_api.RouterOsApiPool(
        settings.MIKROTIK_HOST,
        username=username,
        password=password,
        port=settings.MIKROTIK_PORT,
        use_ssl=settings.MIKROTIK_USE_SSL,
        ssl_verify=settings.MIKROTIK_USE_SSL,
        ssl_verify_hostname=settings.MIKROTIK_USE_SSL,
        plaintext_login=not settings.MIKROTIK_USE_SSL,
    )


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

    read_user = settings.MIKROTIK_READ_USERNAME or settings.MIKROTIK_USERNAME
    read_password = settings.MIKROTIK_READ_PASSWORD or settings.MIKROTIK_PASSWORD
    connection = make_connection(read_user, read_password)
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
            "read_account": read_user,
            "write_probe": "not_run",
        }
        print("Read-only RouterOS acceptance:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        connection.disconnect()

    if args.write_probe:
        control_connection = make_connection(settings.MIKROTIK_USERNAME, settings.MIKROTIK_PASSWORD)
        try:
            api = control_connection.get_api()
            users = api.get_resource("/ip/hotspot/user")
            profile_names = {
                item.get("name")
                for item in api.get_resource("/ip/hotspot/user/profile").get()
            }
            if args.profile not in profile_names:
                raise SystemExit(f"Test profile not found: {args.profile}")
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
                print("Write probe: create verified.")
            finally:
                found = users.get(name=probe_name)
                if found:
                    users.remove(id=found[0].get(".id"))
                print("Write probe cleanup attempted.")
        finally:
            control_connection.disconnect()


if __name__ == "__main__":
    main()
