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
- MIKROTIK_DEMO_MODE=false, with separate operational and read-only RouterOS accounts/passwords reachable only over VPN/private management network. Use API-SSL on port 8729 by default; SmartNet enforces TLS certificate-chain and hostname validation. Configure a RouterOS certificate whose SAN matches MIKROTIK_HOST, and set MIKROTIK_TLS_CA_FILE only when a private CA must be trusted. Never use unencrypted API port 8728 for production credentials. Observer account must have read+api policies only.
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

## Live MikroTik read-only acceptance\nFrom the backend directory, after configuring the real read-only account and trusted RouterOS certificate, run:\n\n~~~bash\npython scripts/mikrotik_readonly_acceptance.py\n~~~\n\nThe command refuses demo mode, uses API-SSL with certificate and hostname verification, prints only router aggregates and active-session count, and performs no mutations. Compare board/version, CPU, free memory and session count with Winbox. Only then use a spare HotSpot profile/account for card-creation and disconnect acceptance. Test reboot separately during a maintenance window.\n\n## Network operations and agents
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

## Wallet Monitoring Agent (backend phase 1)

The first backend slice is implemented on `production-hardening`:
- MariaDB/SQLite-compatible models and Alembic migration `0005_wallet_monitoring` for provider registry, dedicated devices, receiving accounts, payer identities, payment intents, notification events, transaction candidates, reviews and fulfilment records.
- Admin APIs to register provider package allowlists, create/revoke phone devices, configure receiving accounts, approve/revoke payer identities, and inspect events.
- Registration-token and authenticated-client APIs to register payer wallet identities; registration approval links pre-registered wallet identities to the new Client record.
- Device bearer-token APIs for heartbeat and notification events. Device tokens are stored as SHA-256 hashes and displayed once. Event UUIDs are idempotent. Notification title/body are parsed in memory and are not persisted; a payload SHA-256 and normalized candidate fields are retained.
- Candidate matching binds provider, receiving account, the registered device, sender identity, exact amount/currency and one open Payment Intent. Candidate records remain pending review.

### Fail-closed configuration

Keep these values until the Android collector and a real wallet-specific adapter have passed acceptance:
- `WALLET_MONITORING_ENABLED=false` by default. Enable only after setting a unique `WALLET_IDENTITY_HMAC_SECRET` (32+ random characters); production also requires an HTTPS `APP_PUBLIC_URL`.
- `WALLET_AUTO_ACTIVATION_ENABLED=false`. The current application settings intentionally reject `true` because no production wallet parser or live acceptance test is registered.
- The current provider registry stores package allowlists, but there are **no provider-specific parsers registered yet**. Events therefore remain `awaiting_provider_adapter` unless a reviewed parser is added in trusted backend code.
- No Android APK/NotificationListenerService or subscription auto-fulfilment worker is implemented yet. The fulfilment table is preparatory schema only.
- Existing manual payment verification and separate administrator subscription approval remain the supported production path.

### Initial setup sequence

1. Apply `alembic upgrade head` after backing up MariaDB and rehearsing the migration in staging.
2. Keep automatic activation disabled. Generate a unique random `WALLET_IDENTITY_HMAC_SECRET` in the protected service environment; do not place it in Git or chat.
3. Set `WALLET_MONITORING_ENABLED=true` only when the Android collector is ready to use the HTTPS backend.
4. As administrator, register the wallet provider with the exact Android package name from the verified application listing, then create the dedicated monitor device.
5. Transfer the one-time `device_token` to the dedicated phone through a secure channel. Never include it in screenshots, tickets or repository files.
6. Register the receiving wallet account with its provider, device and currency. Add the payer number through the registration token or authenticated client route. The identity approval endpoint rejects approval until a first matching transaction is manually verified against the actual wallet app; after approval it fulfils that first registration/renewal exactly once.
7. Keep incoming events in review until a provider-specific parser is implemented from sanitized real notification examples and passes shadow-mode plus duplicate/reversal tests.

### API paths

- `POST /api/v1/wallet-monitor/admin/providers`
- `POST /api/v1/wallet-monitor/admin/devices` and `POST /api/v1/wallet-monitor/admin/devices/{id}/revoke`
- `POST /api/v1/wallet-monitor/admin/receiving-wallets`
- `POST /api/v1/wallet-monitor/registrations/{registration_id}/payer-wallets`
- `POST /api/v1/wallet-monitor/admin/payer-wallets/{id}/approve`
- `POST /api/v1/wallet-monitor/registrations/{registration_id}/payment-intents`
- `POST /api/v1/wallet-monitor/device/heartbeat` and `POST /api/v1/wallet-monitor/device/events`
- `GET /api/v1/wallet-monitor/admin/events` and `GET /api/v1/wallet-monitor/admin/transactions`
- `POST /api/v1/wallet-monitor/admin/transactions/{transaction_id}/verify` (manual verification against the actual wallet app; first-transfer fulfilment waits for payer identity approval)

See [docs/WALLET_MONITORING_AGENT.md](WALLET_MONITORING_AGENT.md) for the full decision model and remaining phases.

