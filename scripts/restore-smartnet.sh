#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ "${RESTORE_CONFIRM:-}" != "YES" ]]; then
  echo "Refusing destructive restore. Set RESTORE_CONFIRM=YES after verifying the target." >&2
  exit 2
fi
if [[ $# -ne 2 ]]; then
  echo "Usage: RESTORE_CONFIRM=YES $0 <database.sql.gz> <uploads.tar.gz>" >&2
  exit 2
fi
DB_ARCHIVE="$1"
UPLOADS_ARCHIVE="$2"
[[ -f "$DB_ARCHIVE" && -f "$UPLOADS_ARCHIVE" ]] || { echo "Backup file not found." >&2; exit 2; }

set -a
# shellcheck disable=SC1091
source ./.env
set +a
RESTORE_DATABASE="${RESTORE_DATABASE:-$MARIADB_DATABASE}"

gzip -t "$DB_ARCHIVE"
tar -tzf "$UPLOADS_ARCHIVE" >/dev/null
echo "Restoring MariaDB database '$RESTORE_DATABASE' and private uploads."
echo "This overwrites current data. Stop application traffic before proceeding."
gunzip -c "$DB_ARCHIVE" | podman-compose -f podman-compose.yml exec -T mariadb \
  mariadb -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$RESTORE_DATABASE"
podman-compose -f podman-compose.yml exec -T backend tar -xzf - -C /app/backend < "$UPLOADS_ARCHIVE"
echo "Restore completed. Run the post-restore validation checklist in docs/PRODUCTION_RUNBOOK.md."
