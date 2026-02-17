#!/usr/bin/env bash
# Build script for deployment on Railway

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt
pip install -r requirements.native.txt

# Create directories if they don't exist
mkdir -p media
mkdir -p static_collected

# Tests are run in CI before merge - no need to run again here

# Migrations run at deploy time (startCommand in railpack.web.json)
# NOT during build — Railway's database isn't reliably reachable during builds

# Collect static files
echo "Collecting static files..."
DJANGO_SETTINGS_MODULE=flipfix.settings.web python manage.py collectstatic --no-input
echo "✓ Static files collected"
