#!/usr/bin/env bash
set -Eeuo pipefail

: "${MARIADB_DATABASE:?Set MARIADB_DATABASE}"
: "${MARIADB_USER:?Set MARIADB_USER}"
: "${MARIADB_PASSWORD:?Set MARIADB_PASSWORD}"
: "${MARIADB_RESTORE_USER:?Set MARIADB_RESTORE_USER}"
: "${MARIADB_RESTORE_PASSWORD:?Set MARIADB_RESTORE_PASSWORD}"
MARIADB_HOST="${MARIADB_HOST:-127.0.0.1}"
MARIADB_PORT="${MARIADB_PORT:-3306}"
export MARIADB_HOST MARIADB_PORT
MARIADB_BACKUP_DIR="${MARIADB_BACKUP_DIR:-$(mktemp -d)}"
export MARIADB_BACKUP_DIR
mkdir -p "$MARIADB_BACKUP_DIR"
backup_credentials="$(mktemp)"
restore_credentials="$(mktemp)"
trap 'rm -f "$backup_credentials" "$restore_credentials"; rm -rf "$MARIADB_BACKUP_DIR"' EXIT
chmod 600 "$backup_credentials" "$restore_credentials"
cat > "$backup_credentials" <<EOF
[client]
user=$MARIADB_USER
password=$MARIADB_PASSWORD
host=$MARIADB_HOST
port=$MARIADB_PORT
protocol=tcp
default-character-set=utf8mb4
EOF
cat > "$restore_credentials" <<EOF
[client]
user=$MARIADB_RESTORE_USER
password=$MARIADB_RESTORE_PASSWORD
host=$MARIADB_HOST
port=$MARIADB_PORT
protocol=tcp
default-character-set=utf8mb4
EOF

client="$(command -v mariadb)"
"$client" --defaults-extra-file="$restore_credentials" "$MARIADB_DATABASE" <<'SQL'
CREATE TABLE IF NOT EXISTS smartnet_backup_restore_probe (
  id INT PRIMARY KEY,
  marker VARCHAR(80) NOT NULL
) ENGINE=InnoDB;
DELETE FROM smartnet_backup_restore_probe;
INSERT INTO smartnet_backup_restore_probe(id, marker) VALUES (1, 'backup-restore-roundtrip-ok');
SQL

MARIADB_PASSWORD="$MARIADB_PASSWORD" MARIADB_DATABASE="$MARIADB_DATABASE" MARIADB_USER="$MARIADB_USER" \
MARIADB_HOST="$MARIADB_HOST" MARIADB_PORT="$MARIADB_PORT" MARIADB_BACKUP_DIR="$MARIADB_BACKUP_DIR" \
  bash deploy/scripts/backup-mariadb.sh >/dev/null
backup="$(find "$MARIADB_BACKUP_DIR" -maxdepth 1 -type f -name 'smartnet-*.sql.gz' | sort | tail -n 1)"
[[ -n "$backup" ]] || { echo "Backup artifact was not created." >&2; exit 1; }

"$client" --defaults-extra-file="$restore_credentials" "$MARIADB_DATABASE" \
  -e "DROP TABLE smartnet_backup_restore_probe"

MARIADB_RESTORE_USER="$MARIADB_RESTORE_USER" MARIADB_RESTORE_PASSWORD="$MARIADB_RESTORE_PASSWORD" \
MARIADB_DATABASE="$MARIADB_DATABASE" MARIADB_HOST="$MARIADB_HOST" MARIADB_PORT="$MARIADB_PORT" \
  bash deploy/scripts/restore-mariadb.sh --confirm-restore "$backup"

actual="$("$client" --defaults-extra-file="$backup_credentials" --batch --skip-column-names "$MARIADB_DATABASE" \
  -e "SELECT marker FROM smartnet_backup_restore_probe WHERE id=1")"
[[ "$actual" == "backup-restore-roundtrip-ok" ]] || {
  echo "Restored MariaDB data did not match the expected probe." >&2
  exit 1
}
echo "MariaDB backup/restore round-trip passed using separate backup and restore accounts."
