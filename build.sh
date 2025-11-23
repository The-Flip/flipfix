#!/usr/bin/env bash
# Build script for deployment on Railway

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Create media directory if it doesn't exist
mkdir -p media

# Run tests before deploying (fail fast if any test fails)
echo "Running tests..."
make test-ci
echo "✓ All tests passed"

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input
