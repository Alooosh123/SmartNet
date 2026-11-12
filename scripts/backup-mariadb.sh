#!/usr/bin/env bash
set -euo pipefail
BACKUP_ROOT="${BACKUP_ROOT:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
DEST="$BACKUP_ROOT/smartnet-$STAMP"
mkdir -p "$DEST" ./data/uploads ./data/static
trap 'rm -rf "$WORK"' EXIT

echo "Creating transaction-consistent MariaDB dump..."
podman compose exec -T db sh -lc 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump --user=root --single-transaction --routines --triggers --events --hex-blob "$MARIADB_DATABASE"' > "$WORK/database.sql"
echo "Archiving uploads and private static data..."
tar -czf "$WORK/application-data.tar.gz" ./data/uploads ./data/static
cp "$WORK/database.sql" "$DEST/database.sql"
cp "$WORK/application-data.tar.gz" "$DEST/application-data.tar.gz"
(cd "$DEST" && sha256sum database.sql application-data.tar.gz > SHA256SUMS)
echo "Backup completed: $DEST"
echo "Copy off-host and encrypt at rest."
