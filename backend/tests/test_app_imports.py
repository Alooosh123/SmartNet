def test_fastapi_application_imports_and_exposes_core_routes():
    from app import app

    paths = {route.path for route in app.routes}
    assert "/" in paths
    assert "/api/health" in paths
    assert "/api/health/ready" in paths
    assert "/auth/login" in paths
    assert "/auth/register" in paths
    assert "/auth/registrations/{reg_id}/verify-manual" in paths
    assert "/client/chat" in paths
    assert "/mikrotik/status" in paths
    assert "/cards/generate" in paths
