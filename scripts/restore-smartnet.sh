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
podman inspect smartnet-mariadb >/dev/null
podman inspect smartnet-backend >/dev/null
if [[ -z "${RESTORE_UPLOADS_DIR:-}" && "${RESTORE_UPLOADS_CONFIRM:-}" != "YES" ]]; then
  echo "Refusing to overwrite live uploads. Set RESTORE_UPLOADS_DIR for an isolated restore, or RESTORE_UPLOADS_CONFIRM=YES for an intentional in-place restore." >&2
  exit 2
fi

echo "Restoring MariaDB database '$RESTORE_DATABASE'."
echo "Database restore overwrites the selected database. Stop application traffic before proceeding."
gunzip -c "$DB_ARCHIVE" | podman exec -i -e "MYSQL_PWD=$MARIADB_PASSWORD" smartnet-mariadb \
  mariadb -u"$MARIADB_USER" "$RESTORE_DATABASE"

if [[ -n "${RESTORE_UPLOADS_DIR:-}" ]]; then
  mkdir -p "$RESTORE_UPLOADS_DIR"
  tar -xzf "$UPLOADS_ARCHIVE" -C "$RESTORE_UPLOADS_DIR"
  echo "Uploads restored to isolated directory: $RESTORE_UPLOADS_DIR"
else
  echo "Replacing uploads in the running application volume."
  podman exec -i smartnet-backend tar -xzf - -C /app/backend < "$UPLOADS_ARCHIVE"
fi
echo "Restore completed. Run the post-restore validation checklist in docs/PRODUCTION_RUNBOOK.md."
