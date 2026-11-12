#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${1:-}" != "--confirm-restore" || -z "${2:-}" ]]; then
  echo "Usage: $0 --confirm-restore /path/to/smartnet-backup.sql.gz" >&2
  exit 2
fi
backup="$2"
[[ -f "$backup" ]] || { echo "Backup file not found: $backup" >&2; exit 2; }
: "${MARIADB_DATABASE:?Set MARIADB_DATABASE}"
: "${MARIADB_USER:?Set MARIADB_USER}"
: "${MARIADB_PASSWORD:?Set MARIADB_PASSWORD}"
MARIADB_HOST="${MARIADB_HOST:-127.0.0.1}"
MARIADB_PORT="${MARIADB_PORT:-3306}"
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
if [[ -f "$backup.sha256" ]]; then
  sha256sum --check "$backup.sha256"
fi
gzip -dc "$backup" | mariadb --defaults-extra-file="$credentials" "$MARIADB_DATABASE"
echo "Restore completed from: $backup"
