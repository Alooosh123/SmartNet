# SmartNet Security and Production Gate

## Secrets and history

- Never commit `.env`, database files, receipts, router backups, PDFs containing access credentials, or tokens.
- Previous revisions of the repository contained local database and uploaded artifacts. Removing them from the current tree does not erase Git history. Rotate any credentials that may have been present and review repository history/forks before production.
- Use distinct strong secrets for JWT, webhooks, MariaDB application credentials, MariaDB root credentials, dashboard bootstrap and RouterOS.
- Store production values in a protected secret store or service environment. Do not copy production secrets into issue comments or CI logs.

## Runtime and database

- Production uses MariaDB 11.4 and Podman. SQLite is for local development and isolated tests only.
- Do not publish MariaDB port 3306 publicly. The supplied Podman mapping is loopback-only for host administration and integration testing.
- Back up the database and private uploads together, encrypt backups off-host, and test restoration into a separate isolated environment before relying on a backup.
- Run Alembic migrations before the application version that expects the new schema. Take a verified backup before every migration.
- Use rootless Podman on Linux where possible. Keep Caddy or another supported reverse proxy as the public TLS edge.

## MikroTik

- Production must use API-SSL with certificate and hostname validation enabled. Do not fall back to plaintext TCP 8728.
- Keep the management interface reachable only from a VPN/private management network. Never expose RouterOS API ports to the public internet.
- Use a dedicated RouterOS account. The monitoring agent must use read-only permissions; operational credentials should be kept separate where the RouterOS policy model permits it.
- No free-text chat, LLM, diagnostics agent or monitoring agent may execute a configuration change.
- Router changes must use allow-listed actions, request IDs, approval, separate execution, expiry and audit logs. Reboot approval must come from an administrator other than the requester.

## Payments

- A receipt image is not proof of settlement.
- Manual verification records amount, currency, unique external transaction reference and administrator identity. The plan is activated only after a separate approval.
- Duplicate references and amount/currency mismatches must be rejected and reconciled.
- The generic gateway callback is not a provider integration. A real adapter must validate the provider signature, event ID, settled status, amount and currency against official provider documentation before marking payment as verified.

## AI safety

- The monitor and diagnostics agent have read-only data access.
- The diagnostics agent may use only curated repository knowledge and supplied measurements. It must disclose uncertainty and cite the matched local knowledge source.
- Never supply credentials, personal customer data or raw payment details to the model.
- The model cannot approve payments, activate subscriptions, generate credentials on the router, disconnect users, change configuration or reboot a router.
- Human approval is required for high-impact operations; approval and execution are distinct actions.

## Production controls

- Keep `ENVIRONMENT=production`, `PAYMENT_DEMO_MODE=false`, `MIKROTIK_DEMO_MODE=false`, MariaDB and HTTPS-only CORS origins.
- Keep Prometheus metrics administrator-authenticated; do not expose them publicly.
- Configure Sentry only with a protected DSN and ensure request headers, credentials and personal identifiers are scrubbed.
- Monitor failed health checks, authentication abuse, repeated router failures, payment reconciliation anomalies, failed backups and migration errors.
- Review npm and Python security audit output on every release. Do not run blind `npm audit fix --force`; upgrade and retest breaking changes deliberately.
