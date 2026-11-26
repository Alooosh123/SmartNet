from __future__ import annotations

from types import SimpleNamespace
import json

import httpx
import pytest
from fastapi import HTTPException

from api.routes import automation
from api.routes.automation import AgentDispatchRequest, AgentInvokeRequest
from services import n8n_agent_client as client


def n8n_config(**overrides):
    values = {
        "N8N_ENABLED": True,
        "N8N_BASE_URL": "http://127.0.0.1:5678",
        "N8N_WEBHOOK_AUTH_HEADER": "X-SmartNet-Agent-Key",
        "N8N_WEBHOOK_AUTH_VALUE": "x" * 40,
        "N8N_TIMEOUT_SECONDS": 4,
        "ENVIRONMENT": "development",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_n8n_client_posts_only_to_fixed_agent_webhook_and_uses_header_auth():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["header"] = request.headers.get("X-SmartNet-Agent-Key")
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"status": "completed_read_only_inventory"})

    result = await client.invoke_agent(
        "01",
        {"request_id": "test-123", "scope": "public-repository"},
        config=n8n_config(),
        transport=httpx.MockTransport(handler),
    )

    assert result["status"] == "completed_read_only_inventory"
    assert seen["method"] == "POST"
    assert seen["url"] == "http://127.0.0.1:5678/webhook/smartnet/agents/01-repository-auditor"
    assert seen["header"] == "x" * 40
    assert json.loads(seen["body"]) == {"request_id": "test-123"}
    assert "public-repository" not in seen["body"]


@pytest.mark.asyncio
async def test_n8n_client_fails_closed_when_disabled_or_agent_id_is_not_allowlisted():
    with pytest.raises(client.N8nIntegrationDisabled):
        await client.invoke_agent("01", {}, config=n8n_config(N8N_ENABLED=False))

    with pytest.raises(ValueError, match="Unknown SmartNet agent"):
        await client.invoke_agent("99", {}, config=n8n_config())


@pytest.mark.asyncio
async def test_n8n_client_rejects_payload_over_16_kib_and_reserved_keys():
    with pytest.raises(ValueError, match="16 KiB"):
        await client.invoke_agent("01", {"data": "x" * 17_000}, config=n8n_config())

    with pytest.raises(ValueError, match="reserved key"):
        await client.invoke_agent("01", {"constructor": "bad"}, config=n8n_config())


@pytest.mark.asyncio
async def test_n8n_client_rejects_redirects_non_json_and_non_success_responses():
    async def redirect_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(307, headers={"Location": "https://attacker.invalid/"})

    with pytest.raises(client.N8nAgentTransportError, match="HTTP 307"):
        await client.invoke_agent(
            "01", {}, config=n8n_config(), transport=httpx.MockTransport(redirect_handler)
        )

    async def invalid_json_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    with pytest.raises(client.N8nAgentTransportError, match="non-JSON"):
        await client.invoke_agent(
            "01", {}, config=n8n_config(), transport=httpx.MockTransport(invalid_json_handler)
        )


@pytest.mark.asyncio
async def test_n8n_production_bridge_rejects_plain_http():
    config = n8n_config(ENVIRONMENT="production")
    with pytest.raises(client.N8nIntegrationDisabled, match="HTTPS"):
        await client.invoke_agent("01", {}, config=config)


class FakeDatabase:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_supervisor_dispatch_invokes_only_static_child_for_allowed_task(monkeypatch):
    calls = []

    async def fake_invoke(agent_id, payload):
        calls.append((agent_id, payload))
        if agent_id == "00":
            return {
                "status": "dispatch_ready",
                "target_agent": "01-repository-auditor",
                "target_path": "/webhook/smartnet/agents/01-repository-auditor",
            }
        return {"agent": "01-repository-auditor", "status": "completed_read_only_inventory"}

    monkeypatch.setattr(automation, "invoke_agent", fake_invoke)
    db = FakeDatabase()
    result = await automation.dispatch_agent_task(
        AgentDispatchRequest(task="repository_audit", payload={"scope": "safe"}),
        SimpleNamespace(username="owner"),
        db,
    )

    assert [call[0] for call in calls] == ["00", "01"]
    assert calls[1][1]["scope"] == "safe"
    assert result["agent"]["id"] == "01"
    assert result["side_effects_performed"] is False
    assert db.commits == 1
    assert len(db.added) == 1
    assert "safe" not in db.added[0].details


@pytest.mark.asyncio
async def test_supervisor_blocked_result_never_invokes_child(monkeypatch):
    calls = []

    async def fake_invoke(agent_id, payload):
        calls.append(agent_id)
        return {
            "status": "human_approval_required",
            "execution_performed": False,
        }

    monkeypatch.setattr(automation, "invoke_agent", fake_invoke)
    db = FakeDatabase()
    result = await automation.dispatch_agent_task(
        AgentDispatchRequest(task="payment_approval", payload={}),
        SimpleNamespace(username="owner"),
        db,
    )

    assert calls == ["00"]
    assert result["agent_invoked"] is False
    assert db.commits == 1


@pytest.mark.asyncio
async def test_supervisor_route_mismatch_is_rejected_without_child_call(monkeypatch):
    calls = []

    async def fake_invoke(agent_id, payload):
        calls.append(agent_id)
        return {
            "status": "dispatch_ready",
            "target_agent": "12-release-preflight",
            "target_path": "/webhook/attacker-controlled",
        }

    monkeypatch.setattr(automation, "invoke_agent", fake_invoke)
    db = FakeDatabase()
    with pytest.raises(HTTPException) as error:
        await automation.dispatch_agent_task(
            AgentDispatchRequest(task="repository_audit", payload={}),
            SimpleNamespace(username="owner"),
            db,
        )

    assert error.value.status_code == 502
    assert calls == ["00"]
    assert db.commits == 1


def test_dispatch_payload_rejects_dispatcher_controlled_fields_and_large_payloads():
    with pytest.raises(ValueError, match="task وrequest_id"):
        AgentDispatchRequest(task="repository_audit", payload={"task": "production_deploy"})

    with pytest.raises(ValueError, match="16 KiB"):
        AgentInvokeRequest(payload={"data": "x" * 17_000})


@pytest.mark.asyncio
async def test_payment_intake_payload_is_redacted_before_n8n_execution_storage():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={"status": "pending_independent_verification"})

    await client.invoke_agent(
        "08",
        {
            "request_id": "safe-payment-test",
            "provider": "wallet-secret-name",
            "transaction_ref": "TX-PRIVATE-987654",
            "amount": "123.45",
            "currency": "YER",
            "paid_at": "2026-11-26T12:00:00Z",
        },
        config=n8n_config(),
        transport=httpx.MockTransport(handler),
    )

    assert seen["transaction_ref_present"] is True
    assert seen["amount_present"] is True
    assert seen["currency_present"] is True
    assert "TX-PRIVATE-987654" not in str(seen)
    assert "123.45" not in str(seen)
    assert "YER" not in str(seen)
    assert "wallet-secret-name" not in str(seen)


@pytest.mark.asyncio
async def test_financial_reconciliation_sends_only_match_flags_and_issue_codes():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={"status": "needs_finance_review"})

    await client.invoke_agent(
        "09",
        {
            "request_id": "safe-reconciliation-test",
            "expected": {
                "transaction_ref": "EXPECTED-PRIVATE-001",
                "amount": "100.00",
                "currency": "YER",
                "recipient": "PRIVATE-ACCOUNT-01",
            },
            "received": {
                "transaction_ref": "RECEIVED-PRIVATE-002",
                "amount": "110.00",
                "currency": "SAR",
                "recipient": "PRIVATE-ACCOUNT-02",
            },
        },
        config=n8n_config(),
        transport=httpx.MockTransport(handler),
    )

    assert seen["issues"] == [
        "transaction_reference_mismatch",
        "amount_mismatch",
        "currency_mismatch",
        "recipient_mismatch",
    ]
    serialized = str(seen)
    for sensitive in ("EXPECTED-PRIVATE-001", "RECEIVED-PRIVATE-002", "100.00", "110.00", "YER", "SAR", "PRIVATE-ACCOUNT-01"):
        assert sensitive not in serialized
    assert seen["expected"]["amount_present"] is True
    assert seen["received"]["recipient_present"] is True


@pytest.mark.asyncio
async def test_approval_target_and_reason_are_not_sent_to_n8n():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={"status": "awaiting_human_approval"})

    await client.invoke_agent(
        "10",
        {
            "request_id": "safe-approval-test",
            "action": "disconnect_user",
            "target": "private-subscriber-username",
            "reason": "Customer-identifying private incident details",
        },
        config=n8n_config(),
        transport=httpx.MockTransport(handler),
    )

    assert seen["action"] == "disconnect_user"
    assert seen["target_present"] is True
    assert seen["reason_present"] is True
    assert "private-subscriber-username" not in str(seen)
    assert "private incident details" not in str(seen)


@pytest.mark.asyncio
async def test_network_and_health_agents_receive_only_allowlisted_aggregate_data():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={"status": "ok"})

    await client.invoke_agent(
        "07",
        {
            "request_id": "safe-network-test",
            "metrics": {
                "cpu_load_pct": 88,
                "memory_free_pct": 8,
                "active_users_delta": -4,
                "router_password": "never-send-this",
            },
            "observations": ["private address 192.0.2.100 and subscriber name"],
        },
        config=n8n_config(),
        transport=httpx.MockTransport(handler),
    )

    assert seen["metrics"] == {
        "cpu_load_pct": 88,
        "memory_free_pct": 8,
        "active_users_delta": -4,
    }
    assert seen["observations"] == []
    assert "never-send-this" not in str(seen)
    assert "192.0.2.100" not in str(seen)

