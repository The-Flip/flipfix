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

# Run migrations (with retry for database connectivity)
# Railway's private networking can take a moment to initialize
for i in {1..5}; do
  echo "Attempting database migration (attempt $i/5)..."
  if python manage.py migrate; then
    echo "✓ Migrations completed"
    break
  else
    if [ $i -lt 5 ]; then
      echo "Database connection failed, retrying in 5 seconds..."
      sleep 5
    else
      echo "Failed to connect to database after 5 attempts"
      exit 1
    fi
  fi
done

# Collect static files
python manage.py collectstatic --no-input
