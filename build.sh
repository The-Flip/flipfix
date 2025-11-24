#!/usr/bin/env bash
# Build script for deployment on Railway

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Create directories if they don't exist
mkdir -p media
mkdir -p static_collected

# Run tests
echo "Running tests..."
DJANGO_SETTINGS_MODULE=the_flip.settings.test python manage.py test
echo "✓ All tests passed"

# Run migrations
echo "Running migrations..."
DJANGO_SETTINGS_MODULE=the_flip.settings.prod python manage.py migrate
echo "✓ Migrations complete"

# Collect static files
echo "Collecting static files..."
DJANGO_SETTINGS_MODULE=the_flip.settings.prod python manage.py collectstatic --no-input
echo "✓ Static files collected"
