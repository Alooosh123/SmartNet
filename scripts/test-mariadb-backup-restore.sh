#!/usr/bin/env bash
set -euo pipefail
: "${MARIADB_HOST:=127.0.0.1}"
: "${MARIADB_PORT:=3306}"
: "${MARIADB_USER:=root}"
: "${MARIADB_PASSWORD:?Set MARIADB_PASSWORD}"
: "${MARIADB_DATABASE:?Set MARIADB_DATABASE}"
export MYSQL_PWD="$MARIADB_PASSWORD"
RESTORE_DB="${MARIADB_DATABASE}_restore_test"
DUMP="$(mktemp)"
cleanup() {
  mariadb -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" -e \
    "DROP DATABASE IF EXISTS $RESTORE_DB; DROP TABLE IF EXISTS $MARIADB_DATABASE.smartnet_backup_probe" >/dev/null 2>&1 || true
  rm -f "$DUMP"
}
trap cleanup EXIT

mariadb -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" "$MARIADB_DATABASE" <<'SQL'
CREATE TABLE IF NOT EXISTS smartnet_backup_probe (
 id INT PRIMARY KEY,
 marker VARCHAR(100) NOT NULL
) ENGINE=InnoDB;
REPLACE INTO smartnet_backup_probe (id, marker) VALUES (1, 'smartnet-backup-restore-ok');
SQL

mariadb-dump -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" --single-transaction --routines --triggers "$MARIADB_DATABASE" > "$DUMP"
mariadb -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" -e "CREATE DATABASE IF NOT EXISTS $RESTORE_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
mariadb -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" "$RESTORE_DB" < "$DUMP"
MARKER="$(mariadb -N -h "$MARIADB_HOST" -P "$MARIADB_PORT" -u "$MARIADB_USER" "$RESTORE_DB" -e "SELECT marker FROM smartnet_backup_probe WHERE id=1")"
[[ "$MARKER" == "smartnet-backup-restore-ok" ]]
echo "MariaDB dump and restore smoke test passed."
