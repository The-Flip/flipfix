#!/usr/bin/env bash
# Bootstrap the Flipfix development environment.
# Idempotent — safe to run multiple times.
#
# System dependency auto-install works on macOS (Homebrew) and Debian/Ubuntu (apt).
# On other OSes, the script will tell you what to install manually.
#
# What it does:
#   1. Checks Python version (requires 3.13+)
#   2. Installs system dependencies (ffmpeg, libheif) if missing
#   3. Creates a Python venv at .venv (if not present, or recreates if Python too old)
#   4. Installs Python dependencies
#   5. Installs Node.js dependencies (if Node available)
#   6. Installs pre-commit hooks
#   7. Creates required directories
#   8. Sets up .env from .env.example if not present
#   9. Runs database migrations

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Output helpers ---

if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  RED='\033[0;31m'
  NC='\033[0m'
else
  GREEN=''
  YELLOW=''
  RED=''
  NC=''
fi

info() { echo -e "${GREEN}[bootstrap]${NC} $*"; }
warn() { echo -e "${YELLOW}[bootstrap]${NC} $*"; }
fail() { echo -e "${RED}[bootstrap]${NC} $*" >&2; exit 1; }

# --- Python version check ---

PYTHON_CMD="${PYTHON_CMD:-python3}"

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  fail "Python 3 not found. Install Python 3.13+ and try again."
fi

read -r PYTHON_MAJOR PYTHON_MINOR <<< "$("$PYTHON_CMD" -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')"
PYTHON_VERSION="$PYTHON_MAJOR.$PYTHON_MINOR"

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 13 ]; }; then
  fail "Python 3.13+ required (found $PYTHON_VERSION). Update Python and try again."
fi

info "Using Python $PYTHON_VERSION"

# --- System dependencies ---

install_system_deps() {
  local missing=()

  command -v ffmpeg >/dev/null || missing+=(ffmpeg)

  local skipped_check=false

  if [ "$(uname)" = "Darwin" ]; then
    brew list libheif &>/dev/null || missing+=(libheif)
  elif command -v dpkg >/dev/null 2>&1; then
    dpkg -s libheif-dev &>/dev/null || missing+=(libheif)
  else
    warn "Cannot detect libheif on this distro — install it manually if needed."
    skipped_check=true
  fi

  if [ ${#missing[@]} -eq 0 ]; then
    if [ "$skipped_check" = false ]; then
      info "System dependencies already installed."
    fi
    return
  fi

  info "Installing system dependencies: ${missing[*]}"

  if [ "$(uname)" = "Darwin" ]; then
    if ! command -v brew >/dev/null 2>&1; then
      fail "Homebrew not found. Install from https://brew.sh/ and try again."
    fi
    brew install "${missing[@]}"
  elif command -v apt-get >/dev/null 2>&1; then
    local apt_pkgs=()
    for pkg in "${missing[@]}"; do
      case "$pkg" in
        ffmpeg)  apt_pkgs+=(ffmpeg) ;;
        libheif) apt_pkgs+=(libheif1 libheif-dev) ;;
      esac
    done
    if command -v sudo >/dev/null 2>&1; then
      sudo apt-get update -qq && sudo apt-get install -y -qq "${apt_pkgs[@]}"
    else
      apt-get update -qq && apt-get install -y -qq "${apt_pkgs[@]}"
    fi
  else
    warn "Auto-install not supported on this OS. Install manually: ${missing[*]}"
  fi
}

install_system_deps

# --- Python venv ---

VENV_DIR="$REPO_ROOT/.venv"

NEED_VENV=false

if [ ! -d "$VENV_DIR" ]; then
  NEED_VENV=true
elif [ -x "$VENV_DIR/bin/python" ]; then
  read -r VENV_MAJOR VENV_MINOR <<< "$("$VENV_DIR/bin/python" -c 'import sys; print(sys.version_info.major, sys.version_info.minor)')"
  if [ "$VENV_MAJOR" -lt 3 ] || { [ "$VENV_MAJOR" -eq 3 ] && [ "$VENV_MINOR" -lt 13 ]; }; then
    VENV_VERSION="$VENV_MAJOR.$VENV_MINOR"
    warn "Existing venv uses Python $VENV_VERSION — recreating with $PYTHON_VERSION..."
    rm -rf "$VENV_DIR"
    NEED_VENV=true
  fi
else
  warn "Existing venv has no Python binary — recreating..."
  rm -rf "$VENV_DIR"
  NEED_VENV=true
fi

if [ "$NEED_VENV" = true ]; then
  info "Creating Python venv at .venv..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
else
  info "Python venv already exists (Python $VENV_MAJOR.$VENV_MINOR)."
fi

info "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.dev.txt
"$VENV_DIR/bin/pip" install --quiet -r requirements.native.txt || {
  warn "Native dependencies failed to install — HEIF/audio features may be unavailable."
  warn "Install system libraries (libheif-dev, etc.) and re-run 'make bootstrap'."
}

# --- Node.js dependencies ---

if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
  if [ -f package-lock.json ]; then
    info "Installing Node.js dependencies..."
    npm ci --silent
  elif [ -f package.json ]; then
    info "Installing Node.js dependencies..."
    npm install --silent
  fi
else
  warn "Node.js not found — skipping JS dependency install."
  warn "Install Node 22+ for JavaScript tests."
fi

# --- Pre-commit hooks ---

info "Installing pre-commit hooks..."
"$VENV_DIR/bin/pre-commit" install
"$VENV_DIR/bin/pre-commit" install --hook-type pre-push

# --- Required directories ---

mkdir -p media static_collected

# --- .env file ---

if [ ! -f .env ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  "$VENV_DIR/bin/python" -c "
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
DJANGO_SETTINGS_MODULE=flipfix.settings.dev "$VENV_DIR/bin/python" manage.py migrate --no-input

info ""
info "Bootstrap complete! Run 'make runserver' to start developing."
