#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" || ! -f "$BACKUP_DIR/database.sql" ]]; then
  echo "Usage: CONFIRM_RESTORE=YES scripts/restore-mariadb.sh backups/smartnet-<timestamp>" >&2
  exit 2
fi
if [[ "${CONFIRM_RESTORE:-}" != "YES" ]]; then
  echo "This replaces the active database. Stop writes and set CONFIRM_RESTORE=YES." >&2
  exit 3
fi
if [[ -f "$BACKUP_DIR/SHA256SUMS" ]]; then (cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS); fi

podman compose exec -T db sh -lc '
set -eu
case "$MARIADB_DATABASE" in ""|*[!A-Za-z0-9_]*) echo "Unsafe database name" >&2; exit 4;; esac
case "$MARIADB_USER" in ""|*[!A-Za-z0-9_]*) echo "Unsafe database user" >&2; exit 4;; esac
MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --user=root -e "
DROP DATABASE IF EXISTS $MARIADB_DATABASE;
CREATE DATABASE $MARIADB_DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON $MARIADB_DATABASE.* TO '''$MARIADB_USER'''@'''%''';
FLUSH PRIVILEGES;
"
'
podman compose exec -T db sh -lc 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --user=root "$MARIADB_DATABASE"' < "$BACKUP_DIR/database.sql"
echo "Database restored. Restore private files separately, then verify migrations, readiness, records and PDFs."
if [[ -f "$BACKUP_DIR/application-data.tar.gz" ]]; then
  echo "RESTORE_FILES=YES scripts/restore-application-files.sh $BACKUP_DIR/application-data.tar.gz"
fi
