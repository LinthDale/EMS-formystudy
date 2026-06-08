#!/usr/bin/env bash
# Set login passwords for the device-service DB roles (Finding A).
# Secrets come from the environment (.env), NEVER hardcoded / committed.
# Idempotent — ALTER ROLE ... PASSWORD can run repeatedly.
#
# Usage (from repo root, with .env loaded):
#   set -a; source .env; set +a
#   bash infra/timescaledb/set_role_passwords.sh
#
# Requires: DB_AI_PASSWORD, DB_OPS_PASSWORD in env; ems-timescaledb container running.
# Passwords are fed via psql \set (stdin) so they never appear in the process arg list.
set -euo pipefail

: "${DB_AI_PASSWORD:?DB_AI_PASSWORD not set (see .env / .env.example)}"
: "${DB_OPS_PASSWORD:?DB_OPS_PASSWORD not set (see .env / .env.example)}"
CONTAINER="${TIMESCALE_CONTAINER:-ems-timescaledb}"
DB_NAME="${POSTGRES_DB:-ems}"

printf '%s\n' \
  "\\set aipw '${DB_AI_PASSWORD}'" \
  "ALTER ROLE device_service_ai  WITH PASSWORD :'aipw';" \
  "\\set opspw '${DB_OPS_PASSWORD}'" \
  "ALTER ROLE device_service_ops WITH PASSWORD :'opspw';" \
  | docker exec -i "$CONTAINER" psql -U postgres -d "$DB_NAME" -X -v ON_ERROR_STOP=1

echo "device_service_ai / device_service_ops passwords set on ${CONTAINER}/${DB_NAME}."
echo "NOTE: dev pg_hba allows localhost 'trust' (any role, no password). Production must use scram + non-trust pg_hba (Promotion Checklist P-8)."