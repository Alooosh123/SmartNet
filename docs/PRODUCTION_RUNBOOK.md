# SmartNet Production Runbook — MariaDB + Podman

## 1. Supported stack

- MariaDB 12.3 LTS with SQLAlchemy asyncmy.
- Podman and a Compose provider such as podman-compose.
- FastAPI/React may still be run directly on the host for local development.
- On Windows, Podman Desktop uses a Linux Podman Machine/VM; check bind-mount paths and file ownership before production.

Do not use old PostgreSQL or Docker commands from previous documentation in this branch.

## 2. Local development (Windows)

1. Copy root .env.example to backend/.env.
2. Keep ENVIRONMENT=development, PAYMENT_DEMO_MODE=true and MIKROTIK_DEMO_MODE=true; SQLite is acceptable for local development.
3. Backend:
   - cd backend
   - py -3.11 -m venv .venv
   - .\.venv\Scripts\Activate.ps1
   - python -m pip install --upgrade pip
   - pip install -r requirements-dev.txt
   - uvicorn app:app --reload --host 127.0.0.1 --port 8000
4. Frontend in a second terminal:
   - cd frontend
   - Copy-Item .env.example .env.local
   - npm install
   - npm run dev
5. Open http://localhost:5173. Change the development administrator password after login.
6. Tests from backend: python -m compileall -q . then pytest -q tests.

## 3. Podman deployment

Install Podman Engine/Desktop and podman-compose. Prepare a production .env with unique credentials:
- SECRET_KEY and PAYMENT_WEBHOOK_SECRET: 32+ random characters each.
- MARIADB_PASSWORD and MARIADB_ROOT_PASSWORD: separate 24+ character URL-safe secrets.
- GRAFANA_ADMIN_PASSWORD: unique secret if observability profile is enabled.
- Unique non-default DASHBOARD_USERNAME and strong DASHBOARD_PASSWORD.
- ENVIRONMENT=production.
- PAYMENT_PROVIDER_MODE=manual and PAYMENT_DEMO_MODE=false.
- MIKROTIK_DEMO_MODE=false, MIKROTIK_USE_SSL=true, MIKROTIK_PORT=8729.
- MIKROTIK_READ_USERNAME/PASSWORD distinct from the control identity.
- APP_PUBLIC_URL=https://your-domain and CORS_ORIGINS containing exact HTTPS origin(s).

RouterOS API-SSL must have a trusted certificate. Do not disable certificate validation to bypass errors.

Validate and start:
```bash
podman-compose -f compose.yaml config
podman-compose -f compose.yaml up -d --build
podman-compose -f compose.yaml ps
podman-compose -f compose.yaml logs -f backend
```

Web listens on port 8080 by default. Use an HTTPS reverse proxy. Do not publish MariaDB or MikroTik API ports publicly.

Optional Telegram and monitoring:
```bash
podman-compose -f compose.yaml --profile telegram up -d
podman-compose -f compose.yaml --profile observability up -d
```
Prometheus/Grafana bind to localhost ports 9090/3001; use a VPN or local SSH tunnel for administration.

## 4. SQLite to MariaDB data migration

1. Stop all writes to the old application.
2. Back up the SQLite database and private upload/PDF directories.
3. Start a new MariaDB target and run Alembic migrations.
4. Set SOURCE_SQLITE_PATH and the MariaDB DATABASE_URL in a secure environment.
5. Run backend/scripts/migrate_sqlite_to_mariadb.py from the backend working directory.
6. The helper refuses to write to a target containing application rows. It does not delete the source. Compare row counts and sample records, verify registration tokens, client access, payment history, card batches, and receipt/PDF file paths.
7. Keep the original DB and files until business acceptance is complete.

Do not apply this helper to an existing non-empty DB; rehearse on a copy.

## 5. Backup and restore

Create a transaction-consistent database dump, private file archive and SHA-256 checksums:
```bash
scripts/backup-mariadb.sh
```

Copy the resulting backup directory off-host and encrypt at rest.

Restore is destructive and requires a maintenance window after stopping app writes and background jobs:
```bash
CONFIRM_RESTORE=YES scripts/restore-mariadb.sh backups/smartnet-<timestamp>
RESTORE_FILES=YES scripts/restore-application-files.sh backups/smartnet-<timestamp>/application-data.tar.gz
```

After restore run alembic current, health readiness and a customer-to-PDF acceptance scenario before opening traffic. CI has an additional dump/restore test into a separate scratch database; production still requires a scheduled off-host restore drill.

## 6. MikroTik test router

Default acceptance probe is read-only:
```bash
cd backend
python scripts/mikrotik_acceptance.py
```

Optional write probe is only for an isolated test router with a dedicated test Hotspot profile:
```bash
python scripts/mikrotik_acceptance.py --write-probe --confirm-write --profile SmartNet-Test
```

It creates one disabled temporary user and removes it in a finally block. Do not run against a live customer router. Use a private VPN route, valid API-SSL certificate and separate read/control accounts. No live MikroTik acceptance can be reported until real credentials and hardware are supplied.

## 7. Manual payment operating procedure

Production uses manual mode until a named provider and official provider-specific adapter have been implemented and contract-tested.

1. Customer submits a subscription request and uploads an image of the transfer proof.
2. The operator independently verifies actual arrival in the bank/mobile wallet account.
3. The operator records the exact amount, USD currency, method and unique transfer reference in SmartNet.
4. SmartNet stores ManualPayment with verifier and timestamp; this still does not activate the subscription.
5. A separate administrator approval activates the subscription.
6. The Finance Reconciliation page and /auth/payments/reconciliation compare expected and recorded amounts/references and flag exceptions.

Never approve payment from an image, chat message, LLM output or agent conclusion. An automatic gateway requires official docs, sandbox credentials, callback signature verification, unique event ID, settled state, amount/currency matching and idempotency.

## 8. Monitoring and agents

- Network Observer periodically polls RouterOS using its read-only identity.
- Diagnostic Agent correlates telemetry with backend/RouterOS guidance in backend/knowledge/network_troubleshooting.json and returns evidence plus recommended steps.
- Both agents are recommendation/observation-only; no agent executes configuration changes.
- /metrics is for private Prometheus scraping only. Do not publish it through the public Nginx surface.
- Monitor MariaDB health, backend readiness, container restarts, disk capacity, backup age, payment exceptions and router reachability.

## 9. External go-live prerequisites

- Real isolated RouterOS test hardware, API-SSL certificate, network/VPN route, distinct observer/controller accounts and test profile.
- A real account for manual remittance verification, or official payment provider docs and sandbox keys to implement a provider adapter.
- Production domain, HTTPS proxy, secrets, storage and off-host backup destination.
- Restore rehearsal and actual acceptance test before production traffic.
