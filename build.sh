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
# Note: Railway's private networking is not available during build
# We need to use the public database URL if DATABASE_URL uses private networking
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input
