import pytest
from types import SimpleNamespace

from api.routes.mikrotik import _require_plan_for_request
from fastapi import HTTPException
from services.network_observer import evaluate_snapshot
from services.diagnostic_agent import diagnose


@pytest.mark.parametrize(
    "role,plan,action,expected",
    [
        ("client", "monthly", "disconnect", 403),
        ("client", "semi_annual", "disconnect", 0),
        ("client", "semi_annual", "reboot", 403),
        ("client", "annual", "reboot", 0),
        ("admin", "admin", "reboot", 0),
    ],
)
def test_network_action_plan_permissions(role, plan, action, expected):
    current_user = {"role": role, "obj": SimpleNamespace(plan=plan)}
    if expected:
        with pytest.raises(HTTPException) as exc:
            _require_plan_for_request(current_user, action)
        assert exc.value.status_code == expected
    else:
        _require_plan_for_request(current_user, action)


def test_network_observer_alerts_high_cpu_and_low_memory():
    status, alerts = evaluate_snapshot({
        "status": "online", "cpu_load": 97,
        "free_memory_bytes": 100, "total_memory_bytes": 4096,
    })
    assert status == "warning"
    assert any("المعالج" in item for item in alerts)
    assert any("الذاكرة" in item for item in alerts)


def test_network_observer_marks_unreachable_router():
    status, alerts = evaluate_snapshot({"status": "unreachable"})
    assert status == "degraded"
    assert alerts


def test_diagnostic_agent_never_executes_commands():
    metric = SimpleNamespace(
        status="degraded", cpu_load=99, free_memory_bytes=10,
        total_memory_bytes=1000, active_users_count=3,
        alert_summary="router unavailable", observed_at=None,
    )
    result = diagnose(metric)
    assert result["actions_executed"] == []
    assert result["safety"].startswith("التوصيات فقط")
    assert result["findings"]


def test_diagnostic_agent_reports_missing_data():
    result = diagnose(None)
    assert result["status"] == "no_data"
    assert result["findings"][0]["knowledge_id"] == "telemetry-missing"
