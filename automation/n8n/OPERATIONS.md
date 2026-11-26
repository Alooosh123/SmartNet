# SmartNet Automation & Agent Operations

## Agent inventory

Thirteen workflows are provided in `automation/n8n/workflows`. Each source workflow includes AI Agent v3.1, OpenAI Chat Model v1.2 using `gpt-6-luna`, an Arabic system message, minimized context, and a deterministic result finalizer. The registry is `agent-registry.json`; controls are in `approval-policy.json`.

## Local update and testing

After the user has already imported the 13 workflows, do not run the first-time importer again. Use `scripts/Update-And-Test-SmartNetAgents.ps1` on the same Windows account/database:
- backs up all 31 local workflows;
- reads only credential names/IDs from the encrypted credentials export (never decrypted);
- binds the local OpenAI credential and the dedicated `SmartNet Agents Header Auth` credential;
- updates the existing 13 workflow IDs in place;
- re-exports to verify nodes, connections, credentials, and inactive state;
- runs a Manual Trigger OpenAI smoke test for each agent;
- leaves workflows unpublished by default.

See `WINDOWS_INSTALL_AR.md` for local development publication and Backend bridge setup.

## Backend bridge

The optional FastAPI bridge is disabled by default (`N8N_ENABLED=false`). It exposes admin-only:
- `GET /api/v1/automation/agents`
- `POST /api/v1/automation/agents/{agent_id}/invoke`
- `POST /api/v1/automation/dispatch`

The dispatch endpoint asks Supervisor 00 to classify the task, validates its target against a static allow-list, then calls only that fixed webhook path. The Backend never accepts a caller-supplied URL. Production requires an HTTPS n8n origin; the local development origin may be loopback HTTP only. The same `X-SmartNet-Agent-Key` value must be configured in n8n Header Auth and protected Backend environment variables.

## Runtime scope

- 00 classifies and returns a target path; the Backend bridge performs allow-listed dispatch.
- 01 reads the public GitHub repository tree on main; it is not a source-code review.
- 02 checks file path hygiene only; it is not content secret scanning or a dependency audit.
- 06 and 11 call only GET /api/health on webhook execution. Their manual smoke test uses a local fixture to test the model chain and does not prove Backend availability.
- 03, 04, 05, 07, 08, 09, 10, and 12 are input-driven guardrails/review logic. They do not mutate production state.
- AI outputs are advisory and cannot override deterministic decisions.
- No AI tools are connected. No RouterOS, database-write, payment, ledger, or deployment tools are exposed to the model.

## Data minimization

Backend minimizes payloads before calling n8n:
- 01/02/06/11 receive only a request ID.
- 07 receives allow-listed aggregate numeric metrics only; arbitrary observations and identifiers are dropped.
- 08 receives field-presence flags and missing-field names, never payment references, amounts, currencies, or provider identifiers.
- 09 compares expected/received data in Backend memory, then sends mismatch codes and presence flags only.
- 10 receives the action and target/reason presence flags, never target/reason text.
- 03, 04, 05, and 12 receive allow-listed roles/permissions or boolean checklist values.
- 00 receives only task name and request ID.

The Backend audit log records request ID, agent ID, and status only; it does not store request payloads or secrets.

## Local endpoints

The default FastAPI URL used by health workflows is `http://127.0.0.1:8000`. The default local n8n origin is `http://127.0.0.1:5678`. Both must be reachable from the Backend process. If either service runs in a container or a different host, localhost refers to that process/machine; configure the reachable private hostname instead. Production uses HTTPS.

## Security

- All 13 Webhook Trigger nodes require Header Auth in source.
- Credential IDs are bound locally by the updater and never committed to Git.
- Do not publish Webhooks until tests pass, caller integration is configured, and TLS/private-network exposure is checked.
- RouterOS mutations, payment approval, account activation, database restore, and production deployment require durable Backend approval and audit.
- A receipt image is not proof of settlement.

## CLI compatibility

The local updater is restricted to n8n 2.49.5. It uses export/import to back up and update existing workflow IDs, then executes manual smoke tests. It does not automatically publish workflows unless the explicit publication switches and endpoint checks pass.
