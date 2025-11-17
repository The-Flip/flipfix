#!/usr/bin/env bash
# Build script for deployment to test environment on Render.com

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input

# Import legacy maintainers and make some of them admins
python manage.py import_legacy_maintainers

# Create default pinball machines
python manage.py import_machines

# Import legacy maintenance records
python manage.py import_legacy_maintenance_records

