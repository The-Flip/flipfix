#!/usr/bin/env bash
# Build script for web service deployment on Railway

# exit on error
set -o errexit

# Install web service dependencies
pip install -r requirements.web.txt

# Create directories if they don't exist
mkdir -p media
mkdir -p static_collected

# Run migrations
echo "Running migrations..."
DJANGO_SETTINGS_MODULE=the_flip.settings.web python manage.py migrate
echo "✓ Migrations complete"

# Collect static files
echo "Collecting static files..."
DJANGO_SETTINGS_MODULE=the_flip.settings.web python manage.py collectstatic --no-input
echo "✓ Static files collected"
