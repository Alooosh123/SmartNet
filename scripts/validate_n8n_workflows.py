#!/usr/bin/env python3
"""Validate the SmartNet n8n workflow bundle without contacting n8n."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "automation" / "n8n" / "workflows"
EXPECTED = {
    "00-supervisor",
    "01-repository-auditor",
    "02-security-auditor",
    "03-rbac-reviewer",
    "04-database-backup-reviewer",
    "05-mikrotik-test-gate",
    "06-backend-health-monitor",
    "07-network-diagnosis-advisor",
    "08-payment-intake-guard",
    "09-financial-reconciliation",
    "10-human-approval-gate",
    "11-qa-smoke-test",
    "12-release-preflight",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    files = sorted(WORKFLOW_DIR.glob("*.json"))
    actual = {path.stem for path in files}
    if actual != EXPECTED:
        fail(f"Workflow inventory mismatch. Missing={sorted(EXPECTED - actual)}; extra={sorted(actual - EXPECTED)}")

    seen_webhooks: set[str] = set()
    for path in files:
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")

        if workflow.get("active") is not False:
            fail(f"{path.name} must remain inactive in source control")

        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            fail(f"{path.name} has no nodes")

        names = [node.get("name") for node in nodes]
        ids = [node.get("id") for node in nodes]
        if len(names) != len(set(names)) or len(ids) != len(set(ids)):
            fail(f"{path.name} contains duplicate node names or IDs")

        types = {node.get("type") for node in nodes}
        if "n8n-nodes-base.webhook" not in types:
            fail(f"{path.name} has no Webhook Trigger")
        if "n8n-nodes-base.respondToWebhook" not in types:
            fail(f"{path.name} has no Respond to Webhook node")

        webhook_nodes = [node for node in nodes if node.get("type") == "n8n-nodes-base.webhook"]
        if len(webhook_nodes) != 1:
            fail(f"{path.name} must contain exactly one webhook trigger")
        webhook_path = webhook_nodes[0].get("parameters", {}).get("path")
        if not webhook_path or webhook_path in seen_webhooks:
            fail(f"{path.name} has an empty or duplicate webhook path")
        seen_webhooks.add(webhook_path)

        connections = workflow.get("connections", {})
        for source, groups in connections.items():
            if source not in names:
                fail(f"{path.name}: connection source {source!r} does not exist")
            for branch in groups.get("main", []):
                for edge in branch:
                    if edge.get("node") not in names:
                        fail(f"{path.name}: connection target {edge.get('node')!r} does not exist")

        serialized = json.dumps(workflow, ensure_ascii=False)
        for forbidden in (
            "smartnet-super-secret-key-change-in-production-2024",
            "smartnet-webhook-secret-key",
            "admin123",
            "YOUR_GITHUB_TOKEN",
        ):
            if forbidden in serialized:
                fail(f"{path.name} contains a forbidden credential placeholder/default")

    print(f"Validated {len(files)} inactive SmartNet n8n workflows; webhook paths and graph references are unique and valid.")


if __name__ == "__main__":
    main()
