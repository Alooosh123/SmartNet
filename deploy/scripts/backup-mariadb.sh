#!/usr/bin/env bash
set -Eeuo pipefail
: "${MARIADB_DATABASE:?Set MARIADB_DATABASE}"
: "${MARIADB_USER:?Set MARIADB_USER}"
: "${MARIADB_PASSWORD:?Set MARIADB_PASSWORD}"
MARIADB_HOST="${MARIADB_HOST:-127.0.0.1}"
MARIADB_PORT="${MARIADB_PORT:-3306}"
BACKUP_DIR="${MARIADB_BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$BACKUP_DIR/smartnet-$stamp.sql.gz"
credentials="$(mktemp)"
trap 'rm -f "$credentials"' EXIT
chmod 600 "$credentials"
cat > "$credentials" <<EOF
[client]
user=$MARIADB_USER
password=$MARIADB_PASSWORD
host=$MARIADB_HOST
port=$MARIADB_PORT
protocol=tcp
default-character-set=utf8mb4
EOF
mariadb-dump --defaults-extra-file="$credentials" --single-transaction --quick --triggers --hex-blob --add-drop-table "$MARIADB_DATABASE" | gzip -9 > "$destination.tmp"
mv "$destination.tmp" "$destination"
sha256sum "$destination" > "$destination.sha256"
chmod 600 "$destination" "$destination.sha256"
echo "Backup created: $destination"
