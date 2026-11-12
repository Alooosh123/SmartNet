# SmartNet Production Runbook

## 1. Development profile

The local development profile uses SQLite and simulated MikroTik data. It is not production-ready and must never process real subscribers or live router operations.

- Copy `.env.example` to `backend/.env` for the local backend.
- Use `ENVIRONMENT=development`, `DATABASE_BACKEND=sqlite`, `MIKROTIK_DEMO_MODE=true` and `PAYMENT_DEMO_MODE=true` only for local testing.
- Start the API from `backend` using `uvicorn app:app --reload --port 8000`.
- Start the UI from `frontend` using `npm install` and `npm run dev`.
- Run backend unit tests and the Playwright customer lifecycle test before submitting changes.

## 2. MariaDB and Podman deployment

The production target is MariaDB 11.4 + Podman Compose. Docker and PostgreSQL are not used by the supported deployment path. Optional services are started by explicit service name because podman-compose 1.0.6 does not support the Compose `--profile` CLI flag.

1. Install Podman Desktop/Podman and a Compose provider. On Windows initialise and start the Podman machine. On Linux prefer rootless Podman.
2. Copy root `.env.example` to root `.env`; replace every example secret.
3. Set `ENVIRONMENT=production`, `DATABASE_BACKEND=mariadb`, `MARIADB_DATABASE`, `MARIADB_USER`, strong unique `MARIADB_PASSWORD` and `MARIADB_ROOT_PASSWORD`.
4. Set unique 32+ character `SECRET_KEY` and `PAYMENT_WEBHOOK_SECRET`, unique dashboard login and password, exact HTTPS `CORS_ORIGINS`, and real domain / ACME email.
5. Run the environment preflight before starting any service:

```bash
bash scripts/check-production-env.sh
```

The preflight validates secrets, demo flags, TLS settings, separate MikroTik accounts, and HTTPS configuration without printing secret values.
5. Configure RouterOS production settings: `MIKROTIK_DEMO_MODE=false`, `MIKROTIK_USE_SSL=true`, `MIKROTIK_SSL_VERIFY=true`, `MIKROTIK_SSL_VERIFY_HOSTNAME=true`, the secure API-SSL port (normally 8729), router address, a separate read-only monitor account (`MIKROTIK_MONITOR_USERNAME/PASSWORD`) and a separate write-capable operator account (`MIKROTIK_OPERATOR_USERNAME/PASSWORD`). Do not reuse the operator account in the monitoring worker.
6. Set a payment mode. For now `PAYMENT_PROVIDER_MODE=manual` is the complete operational path. Do not choose gateway mode until its provider-specific adapter is implemented and accepted.
7. Start services:

```bash
podman-compose -f podman-compose.yml up -d --build mariadb backend frontend
```

8. Check `http://127.0.0.1:8080/api/health/ready` through the local frontend reverse proxy, API login, and backend readiness. For public HTTPS, point DNS to the host and enable Caddy:

```bash
podman-compose -f podman-compose.yml up -d caddy
```

9. Start Telegram only when the token and numeric admin allow-list have been configured:

```bash
podman-compose -f podman-compose.yml up -d telegram-bot
```

The database port is bound to loopback only. Do not change it to `0.0.0.0:3306`.

### Isolated MariaDB API acceptance test

After the stack reports ready, the repository includes a destructive-to-test-data smoke script that exercises admin login, customer registration, manual payment verification, separate activation, customer login, duplicate transfer-reference rejection, payment reconciliation, and a network-operation request/rejection against the actual MariaDB-backed API.

Run it only against a disposable CI/staging database. It inserts test users and a synthetic payment verification; it does not contact a bank or wallet and it never executes a RouterOS command:

```bash
set -a
source ./.env
set +a
SMARTNET_SMOKE_ALLOW_MUTATIONS=YES \
SMARTNET_SMOKE_CONFIRM_TARGET=isolated-staging-or-ci \
SMARTNET_BASE_URL=http://127.0.0.1:8080 \
python scripts/mariadb_api_smoke.py
```

Never run this smoke script against production customer data. The explicit guard is intentional.

## 3. MariaDB schema and backup/restore

The backend Containerfile runs `alembic upgrade head` before Uvicorn. The first migration baseline was designed for a new SmartNet schema. For any existing installation, back up and review its schema/data before migration; do not apply a baseline blindly.

Backup from a host with Bash and Podman Compose:

```bash
bash scripts/backup-smartnet.sh
```

This creates a MariaDB logical dump, a compressed archive of private uploads, and SHA-256 checksums. Copy the backup off-host and encrypt it.

A restore overwrites database and uploads. Restore only into a verified recovery target after stopping user traffic:

```bash
RESTORE_CONFIRM=YES RESTORE_UPLOADS_CONFIRM=YES bash scripts/restore-smartnet.sh backups/smartnet-db-<UTC>.sql.gz backups/smartnet-uploads-<UTC>.tar.gz
```

Do not run restore against production as a routine test. For a restore drill, leave `RESTORE_UPLOADS_CONFIRM` unset so files extract to a temporary directory, and use a separate MariaDB database. For an intentional in-place recovery, stop app traffic and explicitly set `RESTORE_UPLOADS_CONFIRM=YES`; this replaces the live uploads volume. Verify admin login, customer records, payment evidence, card batches, and PDF file access.

## 4. MikroTik isolated acceptance

Use a dedicated RouterOS test device or an isolated test VLAN/VPN, not the live customer router.

- Install the RouterOS CA certificate into the SmartNet host trust store. The application validates the TLS chain and hostname; it does not silently disable certificate checks. Store separate credentials for `MIKROTIK_MONITOR_*` and `MIKROTIK_OPERATOR_*` in the protected environment.
- Create a dedicated RouterOS user with read-only policy for monitoring. Create a second, separately named operator account with only the policy rights needed for card creation, user disconnection and approved router operations. SmartNet will not use the operator account for telemetry reads.
- Enable API-SSL and restrict the service source address to the SmartNet host/VPN.
- Run the read-only preflight from backend:

```bash
cd backend
python scripts/mikrotik_readonly_acceptance.py
```

- Verify system resource, Hotspot profiles and active sessions. The preflight does not create users, disconnect sessions, change profiles or reboot the router.
- Test a controlled card creation and approved disconnect only after a human operator checks the target/profile and authorises a separate test window. Do not run destructive acceptance tests on a live subscriber network.

The application has no RouterOS address or credentials supplied in this repository. A live acceptance result must be recorded by the operator after running against the dedicated test device.

## 5. Manual payment operating procedure

1. The customer creates a registration request and uploads a receipt image or provides the agreed transfer information.
2. An operator independently checks the wallet/bank statement, exact amount, currency and unique transfer reference.
3. In Admin > Payment requests, enter the verified amount, currency and external reference. SmartNet rejects a mismatch and duplicate reference and records the operator.
4. A separate subscription approval activates the account.
5. Review `GET /auth/payments/reconciliation` periodically and resolve all anomalies before closing the day's settlement.

Receipt uploads never mark a registration as paid. Gateway mode remains unavailable for production until the provider adapter validates signature, event identity, settlement, amount and currency.

## 6. Network monitoring and diagnostics agents

Enable `NETWORK_MONITOR_ENABLED=true` only after the real read-only RouterOS account works. Tune the collection interval, CPU threshold, active-user threshold and alert cooldown. The agent records snapshots and threshold alerts only; it has no write functions.

The Diagnostics Agent searches `backend/knowledge_base` and optionally asks the configured OpenAI model to explain the matched evidence. It must cite its local source and state when measurements are missing. It never executes RouterOS commands.

Admin-only monitoring endpoints:
- `GET /mikrotik/monitor/snapshots`
- `GET /mikrotik/monitor/alerts`
- `GET /api/metrics` (requires administrator authentication)

Diagnostic endpoint:
- `POST /mikrotik/diagnose`

## 7. Prometheus monitoring profile

SmartNet exposes `/api/metrics` only to a dedicated machine token, not to customer JWTs. Production validation requires a strong `METRICS_TOKEN` when metrics are enabled.

1. Set a cryptographically random token in the protected root `.env` as `METRICS_TOKEN`.
2. Create the matching file mounted into Prometheus. Do not commit the `secrets/` directory:

```bash
set -a
. ./.env
set +a
install -d -m 700 secrets
umask 077
printf '%s' "$METRICS_TOKEN" > secrets/metrics-token
```

3. Start the optional internal Prometheus service:

```bash
podman-compose -f podman-compose.yml up -d prometheus
```

4. Confirm `http://127.0.0.1:9090/-/ready` and check the `smartnet-backend` target. Prometheus port 9090 is loopback-only; do not publish it publicly or proxy it through Caddy.
5. Rotate the token in `.env` and the Prometheus token file together, then restart backend and Prometheus.

## 8. Network operation approval workflow

`POST /mikrotik/reboot` and `POST /mikrotik/users/{name}/disconnect` now create pending requests; they do not immediately change the router.

1. A customer or administrator submits an allow-listed operation request.
2. An administrator reviews the target and impact, then approves or rejects.
3. An administrator executes an approved request as a separate step.
4. SmartNet records the requester, reviewer, executor, result and timestamps. Requests expire after 30 minutes.
5. A reboot request cannot be approved by the same administrator who submitted it.

Never allow free-text chat or an AI agent to bypass this workflow.

## 9. Continuous monitoring and release gate

- Keep `/api/health/ready` green and inspect MariaDB connectivity.
- Configure Sentry DSN only through protected environment settings; do not send PII.
- Restrict Prometheus scrape access using the dedicated `METRICS_TOKEN`; keep Prometheus itself on the internal network and loopback-only host binding.
- Review logs for repeated router failures, TLS errors, unexpected operation states, payment anomalies and backup failures.
- Run `npm audit --audit-level=moderate`, `pip-audit -r backend/requirements.txt`, backend tests, Playwright E2E, Podman compose validation and MariaDB migration/restore smoke tests and authenticated Prometheus target-health checks before deployment.
- Complete a real-router acceptance test, manual wallet transfer test, backup restore test, HTTPS check and alert delivery test before onboarding users.

## Remaining external dependencies

No real MikroTik host/certificate/credentials, public DNS domain, payment-provider API credentials or Telegram bot token are present in the repository. The software paths and preflight checks can be prepared here, but live integrations cannot be truthfully marked successful until those external resources are supplied and tested.
