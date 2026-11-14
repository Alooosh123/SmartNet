"""TLS-enforced RouterOS API connection factory.

All SmartNet RouterOS API traffic uses API-SSL. Certificate-chain and hostname
verification are mandatory; an optional private CA file may extend system trust.
"""
from __future__ import annotations

import ssl
from pathlib import Path
from typing import Any

from config.settings import settings

try:
    import routeros_api
except ImportError:  # pragma: no cover - dependency audit/install catches this
    routeros_api = None


def create_routeros_connection(*, host: str, username: str, password: str, port: int) -> Any:
    """Create an API-SSL pool with strict certificate and hostname verification."""
    if routeros_api is None:
        raise RuntimeError("routeros-api is not installed; RouterOS integration is unavailable.")
    if not host or not username or not password:
        raise RuntimeError("RouterOS host, username and password must be configured.")
    if not 1 <= int(port) <= 65535:
        raise RuntimeError("RouterOS API-SSL port must be between 1 and 65535.")

    options: dict[str, Any] = {
        "username": username,
        "password": password,
        "port": int(port),
        "plaintext_login": True,
        "use_ssl": True,
        "ssl_verify": True,
        "ssl_verify_hostname": True,
    }
    ca_file = settings.MIKROTIK_TLS_CA_FILE
    if ca_file:
        ca_path = Path(ca_file).expanduser()
        if not ca_path.is_file():
            raise RuntimeError("MIKROTIK_TLS_CA_FILE does not point to a readable CA certificate file.")
        context = ssl.create_default_context(cafile=str(ca_path))
        # Keep these requirements explicit even when a custom CA is supplied.
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        options["ssl_context"] = context

    return routeros_api.RouterOsApiPool(host, **options)
