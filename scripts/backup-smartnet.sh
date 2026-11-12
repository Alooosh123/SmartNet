#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example and configure it first." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source ./.env
set +a

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${1:-$ROOT_DIR/backups}"
mkdir -p "$DEST"
chmod 700 "$DEST"

podman-compose -f podman-compose.yml exec -T mariadb \
  mariadb-dump --single-transaction --routines --triggers \
  -u"$MARIADB_USER" -p"$MARIADB_PASSWORD" "$MARIADB_DATABASE" \
  | gzip -9 > "$DEST/smartnet-db-$STAMP.sql.gz"

podman-compose -f podman-compose.yml exec -T backend \
  tar -czf - -C /app/backend uploads > "$DEST/smartnet-uploads-$STAMP.tar.gz"

(
  cd "$DEST"
  sha256sum "smartnet-db-$STAMP.sql.gz" "smartnet-uploads-$STAMP.tar.gz" > "smartnet-$STAMP.sha256"
)
chmod 600 "$DEST"/smartnet-*
echo "Backup complete: $DEST/smartnet-$STAMP.sha256"
