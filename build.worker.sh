#!/usr/bin/env bash
# Build script for worker service deployment on Railway

# exit on error
set -o errexit

# Install worker service dependencies
pip install -r requirements.worker.txt

# Create directories if they don't exist
mkdir -p media

# Run migrations (worker needs DB access for task queue)
echo "Running migrations..."
DJANGO_SETTINGS_MODULE=the_flip.settings.prod python manage.py migrate
echo "✓ Migrations complete"
