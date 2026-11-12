# SmartNet Native Production Deployment

This deployment path deliberately uses native services instead of Docker/Compose and MariaDB instead of PostgreSQL.

## 1. Server prerequisites

Recommended: a dedicated Linux server (Ubuntu/Debian) for the production host. Windows Server is supported with native MariaDB and WinSW, but Linux/systemd is the preferred unattended service target.

Install Python 3.11+, Node.js 22.12+ (frontend build only), MariaDB Server 11.8 LTS, Caddy 2, Git and any required build tools.

MariaDB 11.8 is an LTS line with community maintenance through June 2028. Confirm the latest maintenance patch before installation.

References:
- MariaDB supported LTS lines: https://mariadb.org/about/
- MariaDB releases: https://mariadb.org/mariadb/all-releases/
- Caddy install: https://caddyserver.com/docs/install
- Caddy service operation: https://caddyserver.com/docs/running

## 2. Create database and separate privileges

Use utf8mb4. Keep MariaDB bound to loopback when it is on the same machine as SmartNet.

Example SQL (replace every password with a newly generated secret):

~~~sql
CREATE DATABASE smartnet CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'smartnet_app'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_LONG_RANDOM_RUNTIME_SECRET';
GRANT SELECT, INSERT, UPDATE, DELETE ON smartnet.* TO 'smartnet_app'@'127.0.0.1';

CREATE USER 'smartnet_migrator'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_DIFFERENT_LONG_RANDOM_MIGRATION_SECRET';
GRANT ALL PRIVILEGES ON smartnet.* TO 'smartnet_migrator'@'127.0.0.1';

CREATE USER 'smartnet_backup'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_DIFFERENT_LONG_RANDOM_BACKUP_SECRET';
GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES ON smartnet.* TO 'smartnet_backup'@'127.0.0.1';

CREATE USER 'smartnet_restore'@'127.0.0.1' IDENTIFIED BY 'REPLACE_WITH_DIFFERENT_LONG_RANDOM_RESTORE_SECRET';
GRANT ALL PRIVILEGES ON smartnet.* TO 'smartnet_restore'@'127.0.0.1';
FLUSH PRIVILEGES;
~~~

The application account is DML-only. Alembic uses the separate DDL account before service startup. The backup account is read-only apart from metadata/lock privileges required by dump. The separately protected restore account has table-replacement privileges and should only be enabled for a controlled maintenance restore.

Copy .env.example to backend/.env and set at least:

~~~env
ENVIRONMENT=production
DATABASE_URL=mysql+asyncmy://smartnet_app:URL_ENCODED_PASSWORD@127.0.0.1:3306/smartnet?charset=utf8mb4
MIGRATION_DATABASE_URL=mysql+asyncmy://smartnet_migrator:URL_ENCODED_PASSWORD@127.0.0.1:3306/smartnet?charset=utf8mb4
MARIADB_HOST=127.0.0.1
MARIADB_PORT=3306
MARIADB_DATABASE=smartnet
MARIADB_USER=smartnet_backup
MARIADB_PASSWORD=BACKUP_ACCOUNT_PASSWORD
MARIADB_RESTORE_USER=smartnet_restore
MARIADB_RESTORE_PASSWORD=RESTORE_ACCOUNT_PASSWORD
~~~

URL-encode reserved characters in the username/password. Do not reuse one password for all database users. Protect backend/.env so only the service administrator can read it.

## 3. Install and migrate backend

Linux example:

~~~bash
sudo useradd --system --create-home --home-dir /opt/smartnet --shell /usr/sbin/nologin smartnet
sudo mkdir -p /opt/smartnet
sudo chown -R smartnet:smartnet /opt/smartnet
# Deploy the repository into /opt/smartnet, then:
cd /opt/smartnet/backend
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
sudo chown root:smartnet .env
sudo chmod 640 .env
alembic upgrade head
~~~

For Windows PowerShell:

~~~powershell
Set-Location C:\SmartNet\backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
# Create backend\.env with protected production values.
alembic upgrade head
~~~

Production startup deliberately does not call Base.metadata.create_all. Migrations must complete first.

The initial Alembic baseline is intended for a new MariaDB database. Back up existing databases and review migrations before applying them.

## 4. Build the frontend

~~~powershell
Set-Location C:\SmartNet\frontend
npm install
npm audit --audit-level=moderate
npm run build
~~~

On Linux, use the same commands from /opt/smartnet/frontend. Set VITE_API_BASE_URL to an empty string for same-origin production API calls. Development uses http://127.0.0.1:8000.

## 5. Caddy HTTPS and reverse proxy

Edit the root Caddyfile and provide environment variables:
- SMARTNET_DOMAIN — public hostname with DNS A/AAAA records pointing to this server.
- SMARTNET_WEB_ROOT — absolute path to frontend/dist.

Caddy routes /auth, /api, /mikrotik, /cards, /client, /uploads and /static to the local FastAPI process and serves the React SPA from frontend/dist.

Open inbound ports 80 and 443 to Caddy only. Do not expose port 8000, MariaDB 3306 or RouterOS API 8728/8729 to the public internet. Caddy obtains and renews public HTTPS certificates when the domain and ports are correctly configured. For LAN-only use, use an internal CA/certificate approved by the organization.

Linux: install the official Caddy package. Copy Caddyfile to /etc/caddy/Caddyfile, copy deploy/systemd/caddy.env.example to /etc/caddy/caddy.env and replace both values, then copy deploy/systemd/caddy.service.d/override.conf to /etc/systemd/system/caddy.service.d/override.conf. Set root:caddy ownership and mode 0640 on caddy.env. Then:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now caddy
sudo systemctl status caddy
~~~

Windows: install Caddy and download the WinSW x64 service wrapper. Place wrapper copies named smartnet-backend.exe and caddy-service.exe next to their matching XML files in deploy/windows. Edit the domain and site path in caddy-service.xml. Run PowerShell as Administrator:

~~~powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\windows\install-services.ps1
Start-Service smartnet-backend
Start-Service smartnet-caddy
~~~

Note: WinSW service ID is defined inside each XML file; the executable and XML filenames must match. Verify WinSW and Caddy download signatures before installation.

## 6. Start services

Linux:

~~~bash
sudo cp deploy/systemd/smartnet-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smartnet-backend
sudo systemctl status smartnet-backend
~~~

The backend unit runs Alembic before launching Uvicorn. Configure a service user with write permission only to backend/uploads and backend/static. Caddy serves only the frontend build and proxies backend paths; receipts remain served through authenticated API routes, not static URLs.

Windows: start MariaDB first. Then install and start the two WinSW services. The backend reads backend/.env from its working directory.

## 7. Real MikroTik acceptance

Set MIKROTIK_DEMO_MODE=false and route traffic over a private management network or VPN. Keep RouterOS API 8728/8729 inaccessible from the public internet.

Configure two separate RouterOS API accounts:
- Operational account (MIKROTIK_USERNAME / MIKROTIK_PASSWORD): used only by administrator-approved commands such as HotSpot user create/disconnect and router reboot. Grant only the required RouterOS policies and validate them on a test router first.
- Observer account (MIKROTIK_READONLY_USERNAME / MIKROTIK_READONLY_PASSWORD, optionally separate host/port): used by Network Observer and aggregate status endpoint. Assign RouterOS read and api policies only; do not grant write, policy, reboot, password or other administrative policies. The application refuses production configuration when observer username/password are reused from the operational account.

Set MIKROTIK_READONLY_HOST only when the read-only account is exposed on a different management endpoint; otherwise it uses MIKROTIK_HOST. Both accounts must have distinct high-entropy passwords and be reachable only over VPN/private management network.

First acceptance checks should be read-only:
1. GET /api/health/ready
2. GET /mikrotik/status
3. Admin-only GET /mikrotik/users
4. Observe multiple entries in /mikrotik/observations.
5. Compare CPU, free memory, board/version and session count with Winbox.

Only after read-only checks pass, use a spare test HotSpot account/profile to validate card creation and disconnection. Reboot is a separately reviewed destructive operation and should be tested only during a maintenance window with a recovery path. No real router is configured by default.

## 8. Manual payments and reconciliation

Until an official provider API and credentials are supplied, use PAYMENT_PROVIDER_MODE=manual and keep PAYMENT_DEMO_MODE=false in production.

For each transfer:
1. Locate the actual incoming transaction in the wallet/bank channel.
2. Confirm the transaction is settled (not pending/reversed).
3. Enter its unique reference, exact amount, currency and a review note in the admin portal.
4. Only then separately approve the registration.

The backend rejects amount/currency mismatches and duplicate transfer references. Uploading a receipt image never marks payment as received.

Normalized CSV endpoint: POST /auth/reconciliation/statement (administrator only). CSV header row must be compatible with reference,amount,currency,status; accepted settled statuses: settled, paid, completed, success, successful. The endpoint reports matched, mismatched, external-only, internal-only and invalid rows. It does not change payment state or activate customers.

A real gateway requires a provider-specific adapter that verifies official signatures, unique event IDs, settlement state, expected reference, amount and currency. Do not point the generic internal callback directly at an arbitrary provider webhook.

## 9. Backup and restore

Database backups and uploads backups are separate. Back up both:
- MariaDB with deploy/scripts/backup-mariadb.sh (Linux) or deploy/windows/backup-mariadb.ps1 (Windows).
- Private receipts, PDFs and artwork under backend/uploads.

Linux:

~~~bash
export MARIADB_DATABASE=smartnet MARIADB_USER=smartnet_backup MARIADB_PASSWORD='...'
./deploy/scripts/backup-mariadb.sh
tar -czf uploads-$(date -u +%Y%m%dT%H%M%SZ).tar.gz backend/uploads
~~~

Restore is intentionally explicit and overwrites matching tables in the target database:

~~~bash
./deploy/scripts/restore-mariadb.sh --confirm-restore ./backups/smartnet-YYYYMMDDTHHMMSSZ.sql.gz
~~~

Windows PowerShell:

~~~powershell
.\deploy\windows\backup-mariadb.ps1
Compress-Archive -Path .\backend\uploads\* -DestinationPath .\backups\smartnet-uploads.zip
.\deploy\windows\restore-mariadb.ps1 -BackupPath .\backups\smartnet-YYYYMMDDTHHMMSSZ.sql -ConfirmRestore
~~~

Restore only to a maintenance target after verifying backup hash. Restore uploads to the matching application version. Perform a restore rehearsal before launch and regularly thereafter.

## 10. Operations and stop conditions

- Check GET /api/health/ready.
- Review backend service logs and Caddy access/error logs.
- Check /mikrotik/observations and /mikrotik/action-requests as an administrator.
- Confirm NETWORK_OBSERVER_ENABLED=true and sensible thresholds.
- The diagnostic agent uses a curated local MikroTik knowledge base with optional OpenAI assistance. It has no network write tools.
- Do not call the system production-ready until real-router, payment, backup/restore, HTTPS and monitoring acceptance checks are evidenced.

## PostgreSQL transition note

This branch standardizes new production installations on MariaDB. No automatic PostgreSQL-to-MariaDB data converter is included. For a server that already has PostgreSQL customer records, stop writes, create and verify a full backup, export/transform each table and foreign-key relationship into a clean MariaDB staging database, compare row counts and financial totals, verify uploaded-file paths, then plan cutover with a rollback backup. Do not perform an in-place connection-string swap.
