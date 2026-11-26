#!/usr/bin/env python3
"""Validate SmartNet n8n agent workflows and their advisory LLM wiring."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "automation" / "n8n" / "workflows"
REGISTRY_PATH = ROOT / "automation" / "n8n" / "agent-registry.json"
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
AGENT_TYPE = "@n8n/n8n-nodes-langchain.agent"
MODEL_TYPE = "@n8n/n8n-nodes-langchain.lmChatOpenAi"
WEBHOOK_TYPE = "n8n-nodes-base.webhook"
RESPONSE_TYPE = "n8n-nodes-base.respondToWebhook"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{path.relative_to(ROOT)} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def validate_connections(path: Path, workflow: dict[str, Any], node_names: set[str]) -> None:
    connections = workflow.get("connections", {})
    if not isinstance(connections, dict):
        fail(f"{path.name}: connections must be an object")

    for source, groups in connections.items():
        if source not in node_names:
            fail(f"{path.name}: connection source {source!r} does not exist")
        if not isinstance(groups, dict):
            fail(f"{path.name}: connection groups for {source!r} are invalid")
        for connection_type, branches in groups.items():
            if not isinstance(branches, list):
                fail(f"{path.name}: {connection_type} connections for {source!r} must be a list")
            for branch in branches:
                if not isinstance(branch, list):
                    fail(f"{path.name}: malformed {connection_type} branch from {source!r}")
                for edge in branch:
                    target = edge.get("node") if isinstance(edge, dict) else None
                    if target not in node_names:
                        fail(f"{path.name}: connection target {target!r} does not exist")


def one_node(nodes: list[dict[str, Any]], node_type: str, path: Path) -> dict[str, Any]:
    matches = [node for node in nodes if node.get("type") == node_type]
    if len(matches) != 1:
        fail(f"{path.name}: expected exactly one {node_type}; found {len(matches)}")
    return matches[0]


def has_edge(
    connections: dict[str, Any],
    source_name: str,
    connection_type: str,
    target_name: str,
) -> bool:
    branches = connections.get(source_name, {}).get(connection_type, [])
    return any(
        edge.get("node") == target_name
        for branch in branches
        for edge in branch
        if isinstance(edge, dict)
    )


def main() -> None:
    files = sorted(WORKFLOW_DIR.glob("*.json"))
    actual = {path.stem for path in files}
    if actual != EXPECTED:
        fail(
            "Workflow inventory mismatch. "
            f"Missing={sorted(EXPECTED - actual)}; extra={sorted(actual - EXPECTED)}"
        )

    seen_webhooks: set[str] = set()
    all_workflows: dict[str, dict[str, Any]] = {}

    for path in files:
        workflow = load_json(path)
        if workflow.get("active") is not False:
            fail(f"{path.name} must remain inactive in source control")

        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            fail(f"{path.name} has no nodes")
        names = [node.get("name") for node in nodes]
        ids = [node.get("id") for node in nodes]
        if None in names or None in ids or len(names) != len(set(names)) or len(ids) != len(set(ids)):
            fail(f"{path.name} contains missing or duplicate node names/IDs")
        node_names = set(names)

        webhook = one_node(nodes, WEBHOOK_TYPE, path)
        response = one_node(nodes, RESPONSE_TYPE, path)
        agent = one_node(nodes, AGENT_TYPE, path)
        model = one_node(nodes, MODEL_TYPE, path)
        finalizer = next((node for node in nodes if node.get("name") == "Finalize AI Advisory"), None)
        if not finalizer:
            fail(f"{path.name}: deterministic advisory finalizer is missing")
        finalizer_code = finalizer.get("parameters", {}).get("jsCode", "")
        for required_marker in (
            "Manual Trigger - Safe Smoke Test",
            "SMARTNET_OPENAI_SMOKE_TEST_FAILED",
            "SMARTNET_OPENAI_SMOKE_TEST_PASS",
            "if (manualSmokeTest && failed)",
        ):
            if required_marker not in finalizer_code:
                fail(f"{path.name}: real OpenAI smoke-test gate is missing {required_marker!r}")

        manual = [node for node in nodes if node.get("type") == "n8n-nodes-base.manualTrigger"]
        if len(manual) != 1:
            fail(f"{path.name} must contain one Manual Trigger for local smoke testing")

        if webhook.get("parameters", {}).get("authentication") != "headerAuth":
            fail(f"{path.name}: Webhook Trigger must require Header Auth")
        if webhook.get("credentials") or model.get("credentials"):
            fail(f"{path.name}: local credentials must not be committed to Git")
        webhook_path = webhook.get("parameters", {}).get("path")
        if not webhook_path or webhook_path in seen_webhooks:
            fail(f"{path.name} has an empty or duplicate webhook path")
        seen_webhooks.add(webhook_path)

        if agent.get("typeVersion") != 3.1:
            fail(f"{path.name}: AI Agent must use n8n 2.49.5-compatible version 3.1")
        if model.get("typeVersion") != 1.2:
            fail(f"{path.name}: OpenAI Chat Model must use n8n 2.49.5-compatible version 1.2")
        model_selector = model.get("parameters", {}).get("model", {})
        if model_selector.get("value") != "gpt-6-luna" or model_selector.get("mode") != "id":
            fail(f"{path.name}: expected the current OpenAI model ID gpt-6-luna")
        model_options = model.get("parameters", {}).get("options", {})
        if model_options.get("timeout") != 60000 or model_options.get("maxRetries") != 1:
            fail(f"{path.name}: model timeout/retry policy must remain bounded")
        if agent.get("parameters", {}).get("promptType") != "define":
            fail(f"{path.name}: AI Agent must use an explicitly defined prompt")
        agent_options = agent.get("parameters", {}).get("options", {})
        if not agent_options.get("systemMessage"):
            fail(f"{path.name}: Arabic system message is missing")
        if agent_options.get("enableStreaming") is not False:
            fail(f"{path.name}: streaming must be disabled for the guarded request/response flow")
        if agent_options.get("maxIterations", 99) > 3:
            fail(f"{path.name}: AI Agent iteration limit must remain <= 3")

        serialized = json.dumps(workflow, ensure_ascii=False)
        for forbidden in (
            "smartnet-super-secret-key-change-in-production-2024",
            "smartnet-webhook-secret-key",
            "admin123",
            "YOUR_GITHUB_TOKEN",
        ):
            if forbidden in serialized:
                fail(f"{path.name} contains a forbidden credential placeholder/default")

        connections = workflow.get("connections", {})
        validate_connections(path, workflow, node_names)

        if not has_edge(connections, model["name"], "ai_languageModel", agent["name"]):
            fail(f"{path.name}: OpenAI Chat Model is not connected to AI Agent")
        if any("ai_tool" in groups for groups in connections.values()):
            fail(f"{path.name}: AI Agent must not receive an execution tool")
        if not has_edge(connections, agent["name"], "main", "Finalize AI Advisory"):
            fail(f"{path.name}: AI Agent output must pass through Finalize AI Advisory")
        if not has_edge(connections, "Finalize AI Advisory", "main", response["name"]):
            fail(f"{path.name}: final advisory must be returned through Respond to Webhook")

        prep = next((node for node in nodes if node.get("name") == "Prepare Minimized AI Context"), None)
        if not prep or not has_edge(connections, prep["name"], "main", agent["name"]):
            fail(f"{path.name}: minimized context must feed the AI Agent")
        if not has_edge(connections, "Evaluate request", "main", prep["name"]):
            fail(f"{path.name}: deterministic evaluation must precede AI advisory")

        webhook_successors = connections.get(webhook["name"], {}).get("main", [[]])
        manual_successors = connections.get(manual[0]["name"], {}).get("main", [[]])
        if not webhook_successors or not manual_successors:
            fail(f"{path.name}: Webhook and Manual Trigger must both have main connections")

        all_workflows[path.stem] = workflow

    registry = load_json(REGISTRY_PATH)
    updater_path = ROOT / "automation" / "n8n" / "scripts" / "Update-And-Test-SmartNetAgents.ps1"
    try:
        updater_text = updater_path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"Local updater script is missing or unreadable: {exc}")
    for required_updater_marker in (
        "--rawOutput",
        "SMARTNET_OPENAI_SMOKE_TEST_PASS",
        "openai_response_marker_found",
        "export:credentials --all",
        "SmartNet Agents Header Auth",
    ):
        if required_updater_marker not in updater_text:
            fail(f"Local updater is missing real-provider smoke-test requirement {required_updater_marker!r}")

    agents = registry.get("agents", [])
    if len(agents) != 13:
        fail(f"Expected 13 registered agents, found {len(agents)}")

    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    for entry in agents:
        agent_id = str(entry.get("id", ""))
        if agent_id in seen_ids:
            fail(f"Duplicate agent ID in registry: {agent_id}")
        seen_ids.add(agent_id)
        workflow_file = Path(entry.get("file", "")).name
        stem = workflow_file.removesuffix(".json")
        if stem not in all_workflows or workflow_file != f"{stem}.json":
            fail(f"Registry agent {agent_id} points to an unknown workflow")
        if stem in seen_files:
            fail(f"Duplicate workflow reference in registry: {workflow_file}")
        seen_files.add(stem)
        prompt_path = entry.get("prompt_path")
        if not prompt_path:
            fail(f"Agent {agent_id} has no prompt_path")
        target = (ROOT / "automation" / "n8n" / prompt_path).resolve()
        if not target.is_relative_to((ROOT / "automation" / "n8n").resolve()) or not target.is_file():
            fail(f"Agent {agent_id} prompt does not resolve inside automation/n8n")
        if entry.get("llm_status") != "nodes_wired_local_credential_binding_required":
            fail(f"Agent {agent_id} registry LLM status is not truthful/current")
        if entry.get("execution_mode") != "deterministic_guardrail_with_llm_advisory":
            fail(f"Agent {agent_id} execution mode is not the guarded advisory mode")
        if entry.get("credential_binding") is None:
            fail(f"Agent {agent_id} must document local-only credential binding")
        if entry.get("model") != "gpt-6-luna":
            fail(f"Agent {agent_id} registry model must be gpt-6-luna")
        if entry.get("ai_agent_node_version") != "3.1" or entry.get("chat_model_node_version") != "1.2":
            fail(f"Agent {agent_id} registry node versions are not compatible with n8n 2.49.5")
        if entry.get("webhook_authentication") != "headerAuth":
            fail(f"Agent {agent_id} registry must require Header Auth")

    print(
        f"Validated {len(files)} inactive n8n workflows: "
        f"{len(files)} AI Agents, {len(files)} OpenAI Chat Models, "
        f"{len(seen_webhooks)} unique Header Auth webhooks, and {len(agents)} registry entries."
    )
    print("No credential references are stored in source JSON; no AI tools or mutation connections are permitted.")


if __name__ == "__main__":
    main()
