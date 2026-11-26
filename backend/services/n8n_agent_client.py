"""Guarded HTTP client for the local/private SmartNet n8n agent webhooks.

The model can only provide advice. This client exposes no arbitrary URL or tool execution.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from config.settings import settings


AGENT_WEBHOOK_PATHS: dict[str, str] = {
    "00": "smartnet/agents/00-supervisor",
    "01": "smartnet/agents/01-repository-auditor",
    "02": "smartnet/agents/02-security-auditor",
    "03": "smartnet/agents/03-rbac-reviewer",
    "04": "smartnet/agents/04-database-backup-reviewer",
    "05": "smartnet/agents/05-mikrotik-test-gate",
    "06": "smartnet/agents/06-backend-health-monitor",
    "07": "smartnet/agents/07-network-diagnosis-advisor",
    "08": "smartnet/agents/08-payment-intake-guard",
    "09": "smartnet/agents/09-financial-reconciliation",
    "10": "smartnet/agents/10-human-approval-gate",
    "11": "smartnet/agents/11-qa-smoke-test",
    "12": "smartnet/agents/12-release-preflight",
}

AGENT_NAMES: dict[str, str] = {
    "00": "المشرف المركزي",
    "01": "مدقق المستودع",
    "02": "المدقق الأمني",
    "03": "مراجع الصلاحيات",
    "04": "مراجع قاعدة البيانات والنسخ",
    "05": "بوابة اختبار MikroTik",
    "06": "مراقب صحة Backend",
    "07": "مستشار تشخيص الشبكة",
    "08": "حارس استقبال المدفوعات",
    "09": "المطابقة المالية",
    "10": "بوابة الموافقة البشرية",
    "11": "اختبار الجودة الآمن",
    "12": "فحص ما قبل الإصدار",
}

TASK_TO_AGENT: dict[str, str] = {
    "repository_audit": "01",
    "security_audit": "02",
    "rbac_review": "03",
    "database_review": "04",
    "mikrotik_gate": "05",
    "backend_health": "06",
    "network_diagnosis": "07",
    "payment_intake": "08",
    "reconciliation": "09",
    "approval_request": "10",
    "qa_smoke": "11",
    "release_preflight": "12",
}

BLOCKED_TASKS = {
    "router_reboot",
    "disconnect_user",
    "firewall_change",
    "payment_approval",
    "subscription_activation",
    "database_restore",
    "production_deploy",
}


class N8nIntegrationDisabled(RuntimeError):
    """Raised when the optional n8n integration has not been enabled."""


class N8nAgentTransportError(RuntimeError):
    """Raised when a fixed n8n webhook cannot be reached or returns invalid JSON."""


def _validate_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Agent payload must be a JSON object.")
    try:
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Agent payload must contain JSON-compatible values.") from exc
    if len(serialized.encode("utf-8")) > 16_384:
        raise ValueError("Agent payload exceeds the 16 KiB limit.")
    reserved = {"__proto__", "constructor", "prototype"}
    if any(key in reserved for key in payload):
        raise ValueError("Agent payload contains a reserved key.")


def _build_webhook_url(agent_id: str, config: Any = settings) -> str:
    path = AGENT_WEBHOOK_PATHS.get(str(agent_id))
    if not path:
        raise ValueError("Unknown SmartNet agent ID.")
    base_url = (getattr(config, "N8N_BASE_URL", None) or "").rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise N8nIntegrationDisabled("N8N_BASE_URL is not configured as a safe origin.")
    if getattr(config, "ENVIRONMENT", "development").lower() == "production" and parsed.scheme != "https":
        raise N8nIntegrationDisabled("The n8n bridge requires HTTPS in production.")
    return f"{base_url}/webhook/{path}"


async def invoke_agent(
    agent_id: str,
    payload: dict[str, Any],
    *,
    config: Any = settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Invoke one allow-listed SmartNet webhook using the configured Header Auth."""
    if not getattr(config, "N8N_ENABLED", False):
        raise N8nIntegrationDisabled("The SmartNet n8n bridge is disabled.")
    if str(agent_id) not in AGENT_WEBHOOK_PATHS:
        raise ValueError("Unknown SmartNet agent ID.")

    _validate_payload(payload)
    auth_header = getattr(config, "N8N_WEBHOOK_AUTH_HEADER", "")
    auth_value = getattr(config, "N8N_WEBHOOK_AUTH_VALUE", None)
    if not auth_header or not auth_value or len(auth_value) < 32:
        raise N8nIntegrationDisabled("The local n8n Header Auth credential is not configured.")

    url = _build_webhook_url(str(agent_id), config)
    headers = {
        "Accept": "application/json",
        auth_header: auth_value,
    }
    timeout = float(getattr(config, "N8N_TIMEOUT_SECONDS", 12))

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise N8nAgentTransportError("Timed out while contacting the SmartNet n8n agent.") from exc
    except httpx.HTTPError as exc:
        raise N8nAgentTransportError("Could not contact the SmartNet n8n agent.") from exc

    if response.status_code < 200 or response.status_code >= 300:
        raise N8nAgentTransportError(
            f"SmartNet n8n agent returned HTTP {response.status_code}."
        )
    try:
        result = response.json()
    except ValueError as exc:
        raise N8nAgentTransportError("SmartNet n8n agent returned a non-JSON response.") from exc
    if not isinstance(result, dict):
        raise N8nAgentTransportError("SmartNet n8n agent response must be a JSON object.")
    return result
