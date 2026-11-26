# SmartNet Automation & Agent Operations

## Agent inventory

Thirteen workflows are provided in automation/n8n/workflows. Each source workflow now includes AI Agent v3.1, OpenAI Chat Model v1.2, an Arabic system message, minimized context, and a deterministic result finalizer. The registry is agent-registry.json; controls are in approval-policy.json.

## Local update

The original importer is for first-time import only. After the 13 workflows have already been imported into the local n8n database, use scripts/Update-And-Test-SmartNetAgents.ps1 to update the existing workflow IDs in place. It backs up the local workflow set, reads only local credential metadata from the encrypted credentials export, binds local OpenAI and Header Auth credentials, updates the existing 13 workflows, re-exports to verify connections, and executes a manual-trigger smoke test for each agent. It leaves workflows unpublished by default.

## Runtime scope

- 00 classifies and routes to an approved target path, but does not call it.
- 01 reads the public GitHub repository tree on main; it is not a source-code review.
- 02 checks file path hygiene only; it is not content secret scanning or a dependency audit.
- 06 and 11 call only GET /api/health on webhook execution. Their manual smoke test uses a local fixture to test the AI/model chain and does not prove Backend availability.
- 03, 04, 05, 07, 08, 09, 10, and 12 are input-driven guardrails/review logic. They do not mutate production state.
- AI outputs are advisory and cannot override deterministic decisions.
- No AI tools are connected. No RouterOS, database-write, payment, ledger, or deployment tools are exposed to the model.

## Local endpoints

The default FastAPI URL used by health workflows is http://127.0.0.1:8000. If n8n runs in a container, 127.0.0.1 refers to that container, not the Windows host. Supply a host address reachable from n8n when required.

## Security

- All 13 Webhook Trigger nodes require Header Auth in the source workflow.
- Credential IDs are bound locally by the updater and must never be committed.
- Keep workflows unpublished until HTTPS/private-network exposure and credential checks have been verified.
- All RouterOS mutations, payment approval, account activation, database restore and production deployment require durable backend approval and audit.
- A receipt image is not proof of settlement.

## n8n CLI compatibility

The local updater is restricted to n8n 2.49.5. It uses export/import to back up and update existing workflow IDs, and executes manual smoke tests by workflow ID. It does not automatically publish workflows.
