#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing root .env. Copy .env.example and populate production values first." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

fail() { echo "Production environment check failed: $*" >&2; exit 1; }
require_value() { [[ -n "${!1:-}" ]] || fail "$1 is required."; }
require_min_length() {
  local name="$1" minimum="$2" value="${!1:-}"
  [[ -n "$value" && ${#value} -ge "$minimum" ]] || fail "$name must contain at least $minimum characters."
  [[ "$value" != dev-only-* ]] || fail "$name still contains a development-only value."
  case "${value,,}" in password|changeme|smartnet|admin123) fail "$name is a default/weak value.";; esac
}

[[ "${ENVIRONMENT:-}" == "production" ]] || fail "ENVIRONMENT must be production."
[[ "${DATABASE_BACKEND:-}" == "mariadb" ]] || fail "DATABASE_BACKEND must be mariadb."
[[ "${PAYMENT_DEMO_MODE:-true}" == "false" ]] || fail "PAYMENT_DEMO_MODE must be false."
[[ "${MIKROTIK_DEMO_MODE:-true}" == "false" ]] || fail "MIKROTIK_DEMO_MODE must be false."
[[ "${PAYMENT_PROVIDER_MODE:-}" == "manual" ]] || fail "Use PAYMENT_PROVIDER_MODE=manual until a provider-specific adapter is accepted."

require_min_length SECRET_KEY 32
require_min_length PAYMENT_WEBHOOK_SECRET 32
require_min_length DASHBOARD_PASSWORD 12
require_min_length MARIADB_PASSWORD 16
require_min_length MARIADB_ROOT_PASSWORD 20
require_min_length MIKROTIK_MONITOR_PASSWORD 16
require_min_length MIKROTIK_OPERATOR_PASSWORD 16
require_min_length METRICS_TOKEN 32

for name in DASHBOARD_USERNAME MARIADB_HOST MARIADB_DATABASE MARIADB_USER \
  MIKROTIK_HOST MIKROTIK_MONITOR_USERNAME MIKROTIK_OPERATOR_USERNAME DOMAIN ACME_EMAIL; do
  require_value "$name"
done

[[ "${DASHBOARD_USERNAME,,}" != admin && "${DASHBOARD_USERNAME,,}" != administrator ]] || fail "Choose a non-default dashboard username."
[[ "$MARIADB_PASSWORD" != "$MARIADB_ROOT_PASSWORD" ]] || fail "MariaDB application and root passwords must differ."
[[ "$MIKROTIK_MONITOR_USERNAME" != "$MIKROTIK_OPERATOR_USERNAME" ]] || fail "MikroTik monitor and operator accounts must differ."
[[ "$MIKROTIK_MONITOR_PASSWORD" != "$MIKROTIK_OPERATOR_PASSWORD" ]] || fail "MikroTik monitor and operator passwords must differ."
[[ "${MIKROTIK_USE_SSL:-false}" == "true" ]] || fail "MIKROTIK_USE_SSL must be true."
[[ "${MIKROTIK_SSL_VERIFY:-false}" == "true" ]] || fail "MIKROTIK_SSL_VERIFY must be true."
[[ "${MIKROTIK_SSL_VERIFY_HOSTNAME:-false}" == "true" ]] || fail "MIKROTIK_SSL_VERIFY_HOSTNAME must be true."
[[ "${CORS_ORIGINS:-}" == *"https://"* ]] || fail "CORS_ORIGINS must contain an HTTPS origin."
[[ "${CORS_ORIGINS:-}" != *"http://"* ]] || fail "CORS_ORIGINS must not contain insecure HTTP origins."
[[ "${APP_PUBLIC_URL:-}" == https://* ]] || fail "APP_PUBLIC_URL must use HTTPS."

echo "Production environment preflight passed. Secret values were not printed."
