#!/usr/bin/env bash
set -euo pipefail
ARCHIVE="${1:-}"
if [[ "${RESTORE_FILES:-}" != "YES" || -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "Usage: RESTORE_FILES=YES scripts/restore-application-files.sh application-data.tar.gz" >&2
  exit 2
fi
tar -tzf "$ARCHIVE" | grep -Eq '^\./data/(uploads|static)(/|$)' || {
  echo "Unexpected archive contents." >&2
  exit 3
}
mkdir -p ./data
tar -xzf "$ARCHIVE" -C . --no-same-owner
echo "Private data restored; check ownership and permissions before startup."
