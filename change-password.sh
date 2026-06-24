#!/usr/bin/env bash
#
# Change a ContractsPulse user's email and/or password.
#
# Runs the credential-change helper inside the running `api` container so it can
# reach the database. By default it updates the seeded admin account
# (admin@admin.com) and prompts you securely for a new password.
#
# Usage:
#   ./change-password.sh                       # interactive, updates admin@admin.com
#   ./change-password.sh you@example.com       # interactive, updates a specific user
#   NEW_EMAIL=you@example.com ./change-password.sh   # also change the login email
#
# Non-interactive (e.g. scripts/CI):
#   CURRENT_EMAIL=admin@admin.com NEW_PASSWORD='S3cret!' ./change-password.sh
#
set -euo pipefail

# Pick docker compose v2 ("docker compose") or fall back to v1 ("docker-compose").
if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "Error: docker compose is not installed or not on PATH." >&2
  exit 1
fi

# Ensure the api service is up.
if ! $COMPOSE ps --status running api 2>/dev/null | grep -q api; then
  echo "Error: the 'api' service is not running. Start the stack first (./restart.sh)." >&2
  exit 1
fi

# Allow overriding the target email via the first positional arg.
if [ "${1:-}" != "" ]; then
  export CURRENT_EMAIL="$1"
fi

# Forward relevant env vars; use -T when not attached to a TTY (non-interactive).
TTY_FLAG=""
if [ ! -t 0 ]; then
  TTY_FLAG="-T"
fi

exec $COMPOSE exec $TTY_FLAG \
  -e CURRENT_EMAIL="${CURRENT_EMAIL:-admin@admin.com}" \
  -e NEW_EMAIL="${NEW_EMAIL:-}" \
  -e NEW_PASSWORD="${NEW_PASSWORD:-}" \
  api python scripts/change_credentials.py
