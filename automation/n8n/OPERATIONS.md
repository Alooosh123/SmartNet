# SmartNet Automation & Agent Operations

## Agent inventory

Thirteen n8n workflows are provided in `automation/n8n/workflows`. Their registry is `agent-registry.json`; controls are in `approval-policy.json`.

## Import

1. Open the local n8n editor.
2. Import each JSON file from the workflows directory.
3. Keep all workflows inactive while configuring authentication and local host addresses.
4. Configure webhook authentication on every externally reachable workflow.
5. Start with 01 (GitHub inventory), then 06 (FastAPI health), and 11 (safe health smoke test).
6. The supervisor returns a workflow target path; it does not invoke workflows automatically. Activate and connect the dispatcher only after webhook authentication is configured.

## Runtime limitations

- 01 reads GitHub's public repository tree on the main branch.
- 02 checks repository file paths only; it is not a content secret scanner or package vulnerability scanner.
- 06 and 11 check only `GET /api/health`; they do not prove database or router health.
- 03, 04, 05, 07, 08, 09, 10, and 12 are guardrails/review logic. They do not mutate production state.
- No workflow is connected to local n8n during repository authoring. Import and runtime validation on the user's PC remain a separate step.

## Local endpoints

The default FastAPI URL used by health workflows is `http://127.0.0.1:8000`. If n8n runs in a container, `127.0.0.1` refers to that container, not the Windows host. Use the host address reachable from n8n in that case.

## Security

- Never place GitHub, Telegram, OpenAI, MikroTik, payment, JWT, or webhook secrets in workflow JSON or Git.
- Store secrets in n8n Credentials or the local secret environment.
- Keep production workflows inactive until webhook auth, TLS/private network exposure, and role boundaries have been tested.
- All RouterOS mutations, payment approval, account activation, database restore and production deployment require durable backend approval and audit.
- A receipt image is not proof of settlement.


## Windows local import

See [WINDOWS_INSTALL_AR.md](./WINDOWS_INSTALL_AR.md) for the guarded Windows import process. The PowerShell installer backs up the current n8n workflow set, checks for duplicate SmartNet names, and imports the 13 workflows inactive. It never publishes workflows or writes credentials. Webhook authentication and local runtime checks are required before publishing.
