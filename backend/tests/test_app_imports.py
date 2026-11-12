def test_fastapi_application_imports_and_exposes_core_routes():
    from app import app

    # FastAPI's latest router includes may be represented by internal routing
    # wrappers; OpenAPI is the stable public route registry.
    paths = set(app.openapi()["paths"])
    expected = {
        "/", "/api/health", "/api/health/ready",
        "/auth/login", "/auth/register",
        "/auth/registrations/{reg_id}/verify-manual",
        "/auth/payments/reconciliation",
        "/client/chat",
        "/mikrotik/status", "/mikrotik/reboot",
        "/mikrotik/action-requests",
        "/cards/generate",
        "/agents/network/overview",
        "/agents/network/collect",
        "/agents/diagnostics/run",
    }
    assert expected.issubset(paths), f"Missing routes: {expected - paths}"
