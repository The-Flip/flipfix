#!/usr/bin/env bash
# Start an isolated Flipfix dev server for agent-driven checks.
#
# - Throwaway SQLite DB in $RUN_DIR (never touches the Postgres in .env)
# - Maintainer login "runcheck" with a random password in $RUN_DIR/pw
# - runserver on 127.0.0.1:$PORT, log in $RUN_DIR/server.log
# - Playwright installed into $RUN_DIR for driver.mjs
#
# Usage (from the repo root): .claude/skills/run-flipfix/start.sh [--fresh [--sample-data]]
#   --fresh        delete the throwaway DB first
#   --sample-data  load `create_sample_data` (machines, problems, logs...); needs
#                  an empty DB, so use with --fresh. Adds ~10s and writes ~26
#                  files into the repo's (gitignored) media/ dir.
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
RUN_DIR="${RUN_DIR:-${TMPDIR:-/tmp}/flipfix-run}"
PORT="${PORT:-8765}"
export DATABASE_URL="sqlite:///$RUN_DIR/run.db"
export DJANGO_SETTINGS_MODULE=flipfix.settings.dev
# Worker-style tasks (e.g. the wiki media sweep) call the web service over HTTP.
export DJANGO_WEB_SERVICE_URL="http://127.0.0.1:$PORT"
PY="$REPO/.venv/bin/python"

cd "$REPO"
mkdir -p "$RUN_DIR"

# lsof exits 1 when nothing is listening; that's fine.
lsof -ti:"$PORT" -sTCP:LISTEN | xargs -r kill || true
FRESH=0 SAMPLE=0
for arg in "$@"; do
  case "$arg" in
    --fresh) FRESH=1 ;;
    --sample-data) SAMPLE=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done
if (( SAMPLE && !FRESH )); then
  echo "--sample-data needs --fresh (create_sample_data refuses non-empty DBs)" >&2
  exit 2
fi
(( FRESH )) && rm -f "$RUN_DIR/run.db"

"$PY" manage.py migrate --noinput >/dev/null
# Must run before the login user exists: it refuses DBs that already have users.
(( SAMPLE )) && "$PY" manage.py create_sample_data >/dev/null

if [[ ! -s "$RUN_DIR/pw" ]]; then
  python3 -c "import secrets; print(secrets.token_hex(12))" >"$RUN_DIR/pw"
fi
RUN_PW="$(cat "$RUN_DIR/pw")" "$PY" manage.py shell --no-imports -c "
import os
from django.contrib.auth.models import User
from flipfix.apps.core.test_utils import create_maintainer_user
u = User.objects.filter(username='runcheck').first() or create_maintainer_user(username='runcheck')
u.set_password(os.environ['RUN_PW']); u.save()
" >/dev/null  # stderr left visible so a failure here isn't misreported later as "login failed"

if [[ ! -d "$RUN_DIR/node_modules/playwright" ]]; then
  (cd "$RUN_DIR" && npm init -y >/dev/null && npm i playwright@latest >/dev/null 2>&1)
fi

nohup "$PY" manage.py runserver "127.0.0.1:$PORT" --noreload >"$RUN_DIR/server.log" 2>&1 &
timeout 30 bash -c "until curl -sf -o /dev/null http://127.0.0.1:$PORT/login/; do sleep 1; done"

echo "Flipfix up at http://127.0.0.1:$PORT (login runcheck / \$(cat $RUN_DIR/pw))"
echo "RUN_DIR=$RUN_DIR  DATABASE_URL=$DATABASE_URL"
