import ssl
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from services import routeros_connection


def test_routeros_connection_always_uses_tls_and_verifies_certificate_and_hostname(monkeypatch):
    pool_factory = Mock(return_value=object())
    monkeypatch.setattr(routeros_connection, "routeros_api", SimpleNamespace(RouterOsApiPool=pool_factory))
    monkeypatch.setattr(routeros_connection.settings, "MIKROTIK_TLS_CA_FILE", None)

    routeros_connection.create_routeros_connection(
        host="router.example.test",
        username="smartnet-observer",
        password="test-secret",
        port=8729,
    )

    pool_factory.assert_called_once_with(
        "router.example.test",
        username="smartnet-observer",
        password="test-secret",
        port=8729,
        plaintext_login=True,
        use_ssl=True,
        ssl_verify=True,
        ssl_verify_hostname=True,
    )


def test_routeros_connection_uses_custom_ca_without_disabling_verification(tmp_path, monkeypatch):
    ca_file = tmp_path / "router-ca.pem"
    ca_file.write_text("test CA placeholder", encoding="utf-8")
    context = ssl.create_default_context()
    context_factory = Mock(return_value=context)
    pool_factory = Mock(return_value=object())
    monkeypatch.setattr(routeros_connection.ssl, "create_default_context", context_factory)
    monkeypatch.setattr(routeros_connection, "routeros_api", SimpleNamespace(RouterOsApiPool=pool_factory))
    monkeypatch.setattr(routeros_connection.settings, "MIKROTIK_TLS_CA_FILE", str(ca_file))

    routeros_connection.create_routeros_connection(
        host="router.example.test",
        username="smartnet-operator",
        password="test-secret",
        port=8729,
    )

    context_factory.assert_called_once_with(cafile=str(ca_file))
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert pool_factory.call_args.kwargs["ssl_context"] is context
    assert pool_factory.call_args.kwargs["use_ssl"] is True


def test_routeros_connection_rejects_missing_custom_ca(monkeypatch, tmp_path):
    monkeypatch.setattr(routeros_connection, "routeros_api", SimpleNamespace(RouterOsApiPool=Mock()))
    monkeypatch.setattr(routeros_connection.settings, "MIKROTIK_TLS_CA_FILE", str(tmp_path / "missing.pem"))

    with pytest.raises(RuntimeError, match="CA certificate"):
        routeros_connection.create_routeros_connection(
            host="router.example.test",
            username="smartnet-observer",
            password="test-secret",
            port=8729,
        )


def test_routeros_connection_rejects_invalid_port(monkeypatch):
    monkeypatch.setattr(routeros_connection, "routeros_api", SimpleNamespace(RouterOsApiPool=Mock()))
    monkeypatch.setattr(routeros_connection.settings, "MIKROTIK_TLS_CA_FILE", None)

    with pytest.raises(RuntimeError, match="port"):
        routeros_connection.create_routeros_connection(
            host="router.example.test",
            username="smartnet-observer",
            password="test-secret",
            port=70000,
        )


def test_admin_session_listing_uses_readonly_router_account(monkeypatch):
    from types import SimpleNamespace
    from api.routes import mikrotik

    monkeypatch.setattr(
        mikrotik.mikrotik_service,
        "get_active_users",
        lambda: (_ for _ in ()).throw(AssertionError("privileged operational account must not be used for reads")),
    )
    monkeypatch.setattr(mikrotik.mikrotik_readonly_service, "get_active_users", lambda: [{"user": "test-user"}])

    result = mikrotik.get_active_users(current_admin=SimpleNamespace(username="admin"))
    assert result == [{"user": "test-user"}]
