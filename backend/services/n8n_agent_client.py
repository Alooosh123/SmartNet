"""Guarded HTTP client for the local/private SmartNet n8n agent webhooks.

The model can only provide advice. This client exposes no arbitrary URL or tool execution.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
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


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _decimal_equal(left: Any, right: Any) -> bool:
    try:
        if isinstance(left, bool) or isinstance(right, bool):
            return False
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _sanitize_payload_for_agent(agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Drop sensitive data before n8n stores webhook execution input."""
    request_id = payload.get("request_id")
    if agent_id in {"01", "02", "06", "11"}:
        return {"request_id": request_id}
    if agent_id == "08":
        payment = payload.get("payment") if isinstance(payload.get("payment"), dict) else payload
        required = ("provider", "transaction_ref", "amount", "currency", "paid_at")
        missing = [field for field in required if not _present(payment.get(field))]
        return {
            "request_id": request_id,
            "agent": "08-payment-intake-guard",
            "missing_fields": missing,
            "provider_present": _present(payment.get("provider")),
            "transaction_ref_present": _present(payment.get("transaction_ref")),
            "amount_present": _present(payment.get("amount")),
            "currency_present": _present(payment.get("currency")),
            "paid_at_present": _present(payment.get("paid_at")),
        }
    if agent_id == "09":
        expected = payload.get("expected") if isinstance(payload.get("expected"), dict) else {}
        received = payload.get("received") if isinstance(payload.get("received"), dict) else {}
        fields = ("transaction_ref", "amount", "currency", "recipient")
        issues: list[str] = []
        for field in fields:
            left, right = expected.get(field), received.get(field)
            if not (_present(left) and _present(right)):
                continue
            if field == "amount":
                matches = _decimal_equal(left, right)
            elif field == "currency":
                matches = str(left).strip().upper() == str(right).strip().upper()
            else:
                matches = str(left).strip() == str(right).strip()
            if not matches:
                issues.append("transaction_reference_mismatch" if field == "transaction_ref" else f"{field}_mismatch")
        return {
            "request_id": request_id,
            "agent": "09-financial-reconciliation",
            "issues": issues,
            "status": "needs_finance_review" if issues else "candidate_match_not_final",
            "expected": {f"{field}_present": _present(expected.get(field)) for field in fields},
            "received": {f"{field}_present": _present(received.get(field)) for field in fields},
        }
    if agent_id == "10":
        return {
            "request_id": request_id,
            "agent": "10-human-approval-gate",
            "action": payload.get("action"),
            "target_present": _present(payload.get("target")),
            "reason_present": _present(payload.get("reason")),
        }
    if agent_id == "07":
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        safe_metrics = {
            key: value
            for key, value in metrics.items()
            if key in {"cpu_load_pct", "memory_free_pct", "active_users_delta"}
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        }
        return {"request_id": request_id, "metrics": safe_metrics, "observations": []}
    if agent_id == "04":
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        allowed = {"backup_created", "backup_checksum_verified", "restore_test_passed", "migration_status_reviewed", "secrets_externalized", "retention_policy_defined"}
        engine = str(payload.get("database_engine") or "").strip().lower()
        return {
            "request_id": request_id,
            "database_engine": engine if engine in {"sqlite", "mariadb", "mysql"} else "not_provided",
            "checks": {key: checks.get(key) is True for key in allowed},
        }
    if agent_id == "05":
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        allowed = {"isolated_test_router", "dedicated_read_only_account", "trusted_source_ip", "tls_or_private_tunnel", "demo_fallback_disabled_in_test", "backup_export_created"}
        return {"request_id": request_id, "checks": {key: checks.get(key) is True for key in allowed}}
    if agent_id == "12":
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        required = {"secret_scan_passed", "dependency_audit_passed", "rbac_tests_passed", "db_backup_verified", "db_restore_test_passed", "mikrotik_isolated_test_passed", "payment_verification_tested", "approval_audit_tested", "qa_suite_passed", "rollback_plan_ready"}
        return {"request_id": request_id, "checks": {key: checks.get(key) is True for key in required}}
    if agent_id == "03":
        allowed_roles = {"owner", "admin", "finance", "network_operator", "support", "client"}
        allowed_permissions = {"view_network_status", "view_active_users", "generate_cards", "disconnect_user", "reboot_router", "verify_payment", "approve_payment", "manage_admins", "view_audit_logs"}
        roles = payload.get("roles") if isinstance(payload.get("roles"), list) else None
        permissions = payload.get("permissions") if isinstance(payload.get("permissions"), list) else []
        safe_roles = [role for role in roles[:6] if isinstance(role, str) and role in allowed_roles] if roles else None
        safe_permissions = [
            {"role": item.get("role"), "permission": item.get("permission")}
            for item in permissions[:64]
            if isinstance(item, dict) and item.get("role") in allowed_roles and item.get("permission") in allowed_permissions
        ]
        return {"request_id": request_id, "roles": safe_roles, "permissions": safe_permissions}
    return {key: value for key, value in payload.items() if key != "request_id"}

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
    safe_payload = _sanitize_payload_for_agent(str(agent_id), payload)
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
            response = await client.post(url, json=safe_payload, headers=headers)
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
