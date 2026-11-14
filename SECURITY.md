# SmartNet Security and Production Gate

## Current supported architecture

- Backend: FastAPI, SQLAlchemy async and Alembic.
- Production database: MariaDB 11.8 LTS. SQLite is for local development and isolated tests only.
- Deployment: native Linux systemd or Windows WinSW services, with Caddy for HTTPS and reverse proxy.
- PostgreSQL, Docker, Docker Compose and Nginx are not part of the supported production path on this branch.

## Immediate repository hygiene

The Git history has contained a SQLite database, uploaded receipt/card images, generated PDFs and Python bytecode. Removing these files from the current tree does not erase previous Git objects, forks, clones or cached copies.

1. Treat any secrets and any customer/payment evidence that may have been committed as exposed.
2. Rotate the JWT signing key, payment webhook secret, RouterOS operator and observer passwords, Telegram bot token, OpenAI key and any provider credentials that may have appeared in repository history.
3. Review the history and access logs. If private customer or payment data was committed, coordinate a repository history rewrite and notify affected operators as required.
4. Never put .env files, database files, receipt evidence, generated subscriber PDFs, uploads, private certificates or Python bytecode in Git.

## RouterOS transport and accounts

All live RouterOS API sessions must use API-SSL. SmartNet's connection factory enables TLS and certificate-chain and hostname verification; it does not expose an insecure verification bypass.

- Default API-SSL port: TCP 8729. Do not use the unencrypted API service on TCP 8728 for production credentials.
- Configure a certificate on RouterOS API-SSL whose SAN matches the configured RouterOS hostname/IP. Current TLS clients reject API-SSL sessions that have no suitable certificate.
- Use the normal operating-system CA trust store, or set MIKROTIK_TLS_CA_FILE to a protected PEM CA bundle. Do not disable certificate or hostname verification to work around certificate errors.
- Keep RouterOS access on a private management VLAN or VPN. Firewall API-SSL to the SmartNet application host only; never publish it to the internet.
- Use two different RouterOS accounts: an observer with only the required read/API policies, and a separate operational account with only the policies required for approved HotSpot operations.
- The Network Observer and Diagnostic Agent are read-only. They store aggregate metrics and session counts, not subscriber names, IP addresses or MAC addresses. Diagnostic output is advisory and cannot mutate RouterOS.
- Customer disconnect/reboot requests remain pending until a different administrator reviews them. Destructive reboot acceptance belongs in a maintenance window with a recovery path.

## Payment integrity

The supported production mode is PAYMENT_PROVIDER_MODE=manual and PAYMENT_DEMO_MODE=false.

1. A receipt image is supporting evidence only; it never marks a registration as paid.
2. A finance operator independently confirms a settled incoming transfer in the actual wallet/bank account.
3. The reviewer records the unique transfer reference, exact amount, currency and review note.
4. The backend checks amount/currency and prevents duplicate references.
5. A separately authorized administrator approves the subscription after financial verification.
6. CSV statement reconciliation is read-only; it reports matches and discrepancies but never changes payment or subscription status.

No live gateway adapter is claimed. Do not enable gateway mode until an adapter for a named provider verifies its documented signature, event ID, settlement status, SmartNet order/reference, exact amount and currency, with replay/idempotency tests and provider sandbox evidence. Never trust a generic shared-secret callback as proof of provider settlement.

## Production configuration

Set ENVIRONMENT=production and use distinct, randomly generated secrets of at least 32 characters for SECRET_KEY and PAYMENT_WEBHOOK_SECRET. Set a unique dashboard username and strong password. Configure exact HTTPS CORS origins, a MariaDB application account with DML-only permissions, and a separate migration account for Alembic.

Production startup rejects SQLite, demo payment/router modes, non-manual gateway mode, weak secrets, default admin identity and reused MikroTik observer credentials. Keep MariaDB bound to loopback when co-located with SmartNet; expose only Caddy on public TCP 80/443. Keep backend 8000, MariaDB 3306 and RouterOS API-SSL private.

## Rate limits and auditability

Application-level per-client limits cover login, registration, receipt and statement uploads, manual verification, card generation and router reboot. The in-process limiter is scoped to one application process; keep the supported systemd deployment at one worker, and add a shared limiter or edge rate limiting before scaling to multiple workers/replicas. Keep audit logs and operational logs protected.

## Verification before launch

- Run Python dependency audit, backend tests, frontend audit/build and Playwright E2E.
- Run MariaDB migrations and backup/restore drills using separate runtime, migration, backup and restore credentials.
- On an isolated real router, run the read-only command documented in deploy/README.md and compare metrics with Winbox before testing a spare HotSpot user/card.
- Verify a real transfer manually against the actual wallet/bank before entering manual verification. Keep gateway mode disabled.
- Deploy to the real host only after DNS, Caddy HTTPS, service restart, monitoring, off-host backup and restore are proven.
- These repository/CI checks do not prove a live router, a payment-provider connection or a production host is available.
