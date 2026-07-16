#!/usr/bin/env bash
# Refresh the local dev database with (sanitized) production data.
#
#   make sync-prod            # or: scripts/sync_prod.sh [--yes]
#
# What it does:
#   1. pg_dump production (READ-ONLY), excluding secret / history / out-of-scope
#      table DATA so those rows never touch your disk.
#   2. Drop & recreate your LOCAL Postgres database and restore the dump.
#   3. Run scripts/sanitize_dev_db.sql to scrub residual PII.
#   4. Run migrations (a no-op unless your branch has unapplied migrations).
#   5. Create/refresh a dev superuser so you can log in (all prod passwords are
#      scrubbed).
#
# Requirements:
#   - Docker (the local Postgres from docker-compose.yml; started via `make db-up`).
#   - PROD_DATABASE_URL in .env — Railway's *public* connection string
#     (Postgres service -> Variables -> DATABASE_PUBLIC_URL). The internal
#     *.railway.internal host is NOT reachable from your machine.
#   - DATABASE_URL in .env pointing at the local container (see .env.example).
#
# Media files are NOT synced (thumbnails will be broken links locally).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Output helpers ---
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; NC=''
fi
info() { echo -e "${GREEN}[sync-prod]${NC} $*"; }
warn() { echo -e "${YELLOW}[sync-prod]${NC} $*"; }
fail() { echo -e "${RED}[sync-prod]${NC} $*" >&2; exit 1; }

ASSUME_YES=false
[ "${1:-}" = "--yes" ] && ASSUME_YES=true

PYTHON="$(test -x .venv/bin/python && echo .venv/bin/python || echo python3)"

# --- Read a variable from the environment, falling back to .env ---
read_env_var() {
  local name="$1" val="${!1:-}"
  if [ -z "$val" ] && [ -f .env ]; then
    # Last matching, uncommented assignment wins; strip surrounding quotes.
    val="$(grep -E "^${name}=" .env | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e "s/^'//" -e 's/"$//' -e "s/'$//")"
  fi
  printf '%s' "$val"
}

# --- Local Postgres connection (the docker-compose "db" service) ---
LOCAL_URL="$(read_env_var DATABASE_URL)"
LOCAL_URL="${LOCAL_URL:-postgres://flipfix:flipfix@localhost:54321/flipfix}"  # pragma: allowlist secret
case "$LOCAL_URL" in
  *localhost*|*127.0.0.1*) : ;;
  *) fail "DATABASE_URL must point at your LOCAL Postgres (localhost). Got a non-local host — refusing to drop/overwrite it." ;;
esac
# Database name to restore into (last path segment of the URL).
LOCAL_DB="$(printf '%s' "$LOCAL_URL" | sed -E 's#.*/([^/?]+).*#\1#')"

# --- Production source (read-only) ---
PROD_URL="$(read_env_var PROD_DATABASE_URL)"
[ -n "$PROD_URL" ] || fail "PROD_DATABASE_URL is not set (env or .env). See .env.example."
case "$PROD_URL" in
  *railway.internal*) fail "PROD_DATABASE_URL is the internal Railway host, unreachable from your machine. Use DATABASE_PUBLIC_URL instead." ;;
  postgres://*|postgresql://*) : ;;
  *) fail "PROD_DATABASE_URL must be a postgres:// URL." ;;
esac

DC="docker compose"
$DC version >/dev/null 2>&1 || fail "Docker Compose not available. Install Docker Desktop / the compose plugin."

# --- Confirm (destructive) ---
warn "This will DROP and rebuild your local database '${LOCAL_DB}' from production."
warn "Production is read only; nothing there is modified. Local data is replaced."
if [ "$ASSUME_YES" != true ]; then
  read -r -p "Type 'yes' to continue: " reply
  [ "$reply" = "yes" ] || fail "Aborted."
fi

# --- Ensure the local db container is up and accepting connections ---
info "Starting local Postgres container..."
$DC up -d db >/dev/null
info "Waiting for Postgres to be ready..."
for _ in $(seq 1 30); do
  if $DC exec -T db pg_isready -U flipfix -d postgres >/dev/null 2>&1; then break; fi
  sleep 1
done
$DC exec -T db pg_isready -U flipfix -d postgres >/dev/null 2>&1 \
  || fail "Local Postgres did not become ready."

# --- Dump production (read-only), secrets/history/out-of-scope data excluded ---
DUMP="$(mktemp "${TMPDIR:-/tmp}/flipfix-prod-dump.XXXXXX.sql")"
cleanup() { rm -f "$DUMP"; }
trap cleanup EXIT

# --exclude-table-data keeps each table's DDL (so schema + django_migrations stay
# consistent and `migrate` is a no-op) while omitting its rows. Patterns are
# quoted so the shell does not glob them; pg_dump treats * as a wildcard.
# PGOPTIONS forces the prod session read-only so pg_dump physically cannot write,
# on top of pg_dump only ever issuing SELECT/COPY.
info "Dumping production (read-only)... this can take a moment."
$DC exec -T -e PGOPTIONS='-c default_transaction_read_only=on' db pg_dump "$PROD_URL" \
  --no-owner --no-privileges \
  --exclude-table-data='public.*historical*' \
  --exclude-table-data='public.constance_*' \
  --exclude-table-data='public.oauth2_provider_*' \
  --exclude-table-data='public.oauth_*' \
  --exclude-table-data='public.core_apikey' \
  --exclude-table-data='public.accounts_invitation' \
  --exclude-table-data='public.django_session' \
  --exclude-table-data='public.django_admin_log' \
  --exclude-table-data='public.django_q_*' \
  --exclude-table-data='public.parts_*' \
  --exclude-table-data='public.wiki_*' \
  --exclude-table-data='public.discord_*' \
  --exclude-table-data='public.catalog_machinecomment' \
  --exclude-table-data='public.catalog_ownercomment' \
  --exclude-table-data='public.catalog_ownerdocument' \
  > "$DUMP"
info "Dump written ($(wc -c < "$DUMP" | tr -d ' ') bytes)."

# --- Recreate the local database (connect via the maintenance 'postgres' db) ---
info "Recreating local database '${LOCAL_DB}'..."
$DC exec -T db psql -U flipfix -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS ${LOCAL_DB} WITH (FORCE);" \
  -c "CREATE DATABASE ${LOCAL_DB} OWNER flipfix;" >/dev/null

# --- Restore ---
info "Restoring dump into '${LOCAL_DB}'..."
$DC exec -T db psql -U flipfix -d "${LOCAL_DB}" -v ON_ERROR_STOP=1 --quiet < "$DUMP" >/dev/null

# --- Sanitize (scrub residual PII; belt-and-suspenders truncations) ---
info "Sanitizing (scrubbing PII)..."
$DC exec -T db psql -U flipfix -d "${LOCAL_DB}" -v ON_ERROR_STOP=1 --quiet < scripts/sanitize_dev_db.sql >/dev/null

# --- Migrate (should be a no-op; surfaces branch/prod migration drift) ---
info "Applying migrations (no-op unless your branch is ahead of prod)..."
DATABASE_URL="$LOCAL_URL" DJANGO_SETTINGS_MODULE=flipfix.settings.dev \
  "$PYTHON" manage.py migrate --no-input

# --- Ensure a login exists (all prod passwords were scrubbed) ---
DEV_SUPERUSER="${DEV_SUPERUSER:-admin}"
DEV_PASSWORD="${DEV_PASSWORD:-admin}"
info "Ensuring dev superuser '${DEV_SUPERUSER}' exists..."
DATABASE_URL="$LOCAL_URL" DJANGO_SETTINGS_MODULE=flipfix.settings.dev \
  DEV_SUPERUSER="$DEV_SUPERUSER" DEV_PASSWORD="$DEV_PASSWORD" \
  "$PYTHON" manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["DEV_SUPERUSER"]
password = os.environ["DEV_PASSWORD"]
user, _ = User.objects.get_or_create(
    username=username,
    defaults={"email": f"{username}@example.test"},
)
user.is_staff = True
user.is_superuser = True
user.is_active = True
user.set_password(password)
user.save()
print(f"  superuser ready: {username}")
PY

info ""
info "Done. Local DB '${LOCAL_DB}' now holds sanitized production data."
info "Log in at http://localhost:8000/admin/ as '${DEV_SUPERUSER}' / '${DEV_PASSWORD}'."
warn "Media files were not synced — image/video thumbnails will be broken locally."
