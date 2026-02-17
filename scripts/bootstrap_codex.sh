#!/usr/bin/env bash
# Bootstrap the Flipfix development environment for OpenAI Codex cloud.
#
# The Codex UI "Setup" field should run: bash scripts/bootstrap_codex.sh
# This runs WITH internet access before the agent phase begins.
#
# Prerequisites (set in Codex environment settings):
#   - Python: 3.14 (or 3.13)
#   - Node: 22
#
# What it does:
#   1. Verifies Python version (requires 3.13+)
#   2. Installs system dependencies (ffmpeg, libheif)
#   3. Installs Python dependencies (no venv — uses pyenv-managed Python)
#   4. Installs Node.js dependencies
#   5. Creates .env with generated SECRET_KEY
#   6. Creates required directories
#   7. Runs database migrations

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Output helpers ---

info() { echo "[codex-setup] $*"; }
warn() { echo "[codex-setup] WARNING: $*"; }
fail() { echo "[codex-setup] ERROR: $*" >&2; exit 1; }

# --- Python version check ---

PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
PYTHON_VERSION="$PYTHON_MAJOR.$PYTHON_MINOR"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 13 ]; }; then
  fail "Python 3.13+ required (found $PYTHON_VERSION). Pin Python 3.14 in Codex environment settings."
fi

info "Using Python $PYTHON_VERSION"

# --- System dependencies ---

info "Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq ffmpeg libheif1 libheif-dev

# --- Python dependencies ---

info "Installing Python dependencies..."
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.dev.txt
python3 -m pip install --quiet -r requirements.native.txt || {
  warn "Native dependencies failed — HEIF/audio features may be unavailable."
}

# --- Node.js dependencies ---

info "Installing Node.js dependencies..."
npm ci --silent

# --- Required directories ---

mkdir -p media static_collected

# --- .env file ---

if [ ! -f .env ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  python3 -c "
import pathlib
from django.core.management.utils import get_random_secret_key
env = pathlib.Path('.env')
key = get_random_secret_key()
env.write_text(env.read_text().replace('SECRET_KEY=change-me', \"SECRET_KEY='\" + key + \"'\"))
"
  info ".env created with generated SECRET_KEY."
else
  info ".env already exists."
fi

# --- Database migrations ---

info "Running database migrations..."
DJANGO_SETTINGS_MODULE=flipfix.settings.dev python3 manage.py migrate --no-input

info "Codex setup complete."
