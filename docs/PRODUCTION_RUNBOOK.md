# SmartNet Production Runbook (Native Services)

## Local development
1. Copy root .env.example to backend/.env.
2. Keep ENVIRONMENT=development, PAYMENT_DEMO_MODE=true and MIKROTIK_DEMO_MODE=true only for isolated development.
3. From backend: create Python 3.11 venv, install requirements-dev.txt and run uvicorn app:app --reload --host 127.0.0.1 --port 8000.
4. From frontend: copy .env.example to .env.local, run npm install and npm run dev.
5. Open http://127.0.0.1:5173. The first development administrator is created from DASHBOARD_USERNAME and DASHBOARD_PASSWORD. Change it after first login.
6. Optional Telegram bot: python -m bot.main_bot, with a real bot token and numeric admin IDs.

## Production stack
- MariaDB 11.8 LTS replaces PostgreSQL.
- Caddy 2 handles HTTPS, reverse proxy and frontend static assets.
- Native Windows services via WinSW or Linux systemd replace Docker/Compose.
- SQLAlchemy asynchronous database driver: asyncmy.
- No Docker, Docker Compose or Nginx deployment assets remain in this branch.

Do not change a PostgreSQL connection string to MariaDB and assume data has migrated. Existing PostgreSQL data requires a verified backup and a staging export/transform/import, with row counts, financial totals, relationships and file paths checked before cutover.

## Required production environment
- ENVIRONMENT=production.
- Unique random SECRET_KEY and PAYMENT_WEBHOOK_SECRET, each 32+ characters.
- Non-default DASHBOARD_USERNAME and strong unique DASHBOARD_PASSWORD.
- DATABASE_URL=mysql+asyncmy://... to MariaDB 11.8.
- MIGRATION_DATABASE_URL=mysql+asyncmy://... with a dedicated DDL account, separate from the runtime account.
- PAYMENT_PROVIDER_MODE=manual until a provider-specific adapter is implemented and validated.
- PAYMENT_DEMO_MODE=false.
- MIKROTIK_DEMO_MODE=false, with separate operational and read-only RouterOS accounts/passwords reachable only over VPN/private management network. Observer account must have read+api policies only.
- Exact HTTPS CORS_ORIGINS.
- MARIADB_* backup environment variables.
- NETWORK_OBSERVER_ENABLED=true and reviewed thresholds.

Runtime DB account should have SELECT/INSERT/UPDATE/DELETE only. Alembic migration runs use the separate DDL-capable account. Store secrets in protected service environment or a secrets manager.

## Deployment procedure
Follow deploy/README.md for the full installation guide.
1. Install MariaDB and create database, application, migration and backup accounts.
2. Create protected backend/.env; URL-encode reserved characters inside SQLAlchemy URLs.
3. Create the Python environment and install backend/requirements.txt.
4. Build frontend with npm install, npm audit --audit-level=moderate and npm run build.
5. Run alembic upgrade head explicitly before starting the backend.
6. Configure Caddy with the public domain and frontend/dist; validate HTTPS.
7. Install and start the backend service using systemd or WinSW.
8. Expose only ports 80/443. Keep backend 8000 and MariaDB 3306 private. Never expose RouterOS API publicly.
9. Verify /api/health/ready, authentication, authorization, private receipt/PDF access, network observations and audit logs.
10. Complete controlled MikroTik and payment acceptance checks before serving real subscribers.

## Manual payment operations
Until official provider API docs and sandbox/live credentials are supplied, use manual transfer verification:
1. Customer creates a registration and may upload a receipt image.
2. Finance reviewer independently checks the settled incoming transfer in the wallet/bank account.
3. Reviewer enters unique transaction reference, exact amount, currency and explanatory note.
4. Backend checks expected amount/currency and rejects a reused reference.
5. A separately authorized administrator approves the subscription.
6. Use the financial report and normalized CSV upload to identify matched, mismatched, external-only and internal-only records. CSV reconciliation is read-only and does not activate accounts.
Receipt images alone never count as payment. A real gateway needs a provider-specific adapter validating signatures, event IDs, settlement, registration reference, amount and currency.

## Network operations and agents
- Network Observer reads RouterOS resources and active sessions only; it stores aggregate metrics and does not write to RouterOS.
- Diagnostic agent uses observations and a curated MikroTik reference file; optional OpenAI adds natural-language summarization, with no RouterOS action tools.
- Annual/semi-annual customers can request permitted operations; network-changing customer actions require administrator review before execution.
- /mikrotik/users and detailed session identities are administrator-only.

## Backup and restore
Back up MariaDB and backend/uploads separately.
- Linux: deploy/scripts/backup-mariadb.sh and deploy/scripts/restore-mariadb.sh.
- Windows: deploy/windows/backup-mariadb.ps1 and deploy/windows/restore-mariadb.ps1.
Restore scripts require explicit confirmation. Verify SHA256 and rehearse restoration of both database and uploads in a maintenance environment before launch.

## Security and production blockers
- Run pip-audit -r backend/requirements.txt --strict and npm audit --audit-level=moderate.
- CI must pass compile, backend tests, browser E2E, dependency audits, MariaDB migrations and backup/restore.
- Real MikroTik connection cannot be verified until an isolated router and credentials are supplied.
- Real provider payment cannot be verified until a provider is selected and official API/sandbox credentials are supplied; manual transfer review is the operational option meanwhile.
- Production deploy cannot be verified until domain, TLS, target host and rollback plan are available.
- Back up the database and uploads and perform a successful restore before launch.
- Rotate credentials previously committed in Git history; removing files from the current tree does not remove history.