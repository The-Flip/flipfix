#!/usr/bin/env bash
# Build script for deployment to test environment on Render.com

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Change to the Django project directory
cd the_flip

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input

# Import legacy maintainers and make some of them admins
python manage.py import_legacy_maintainers

# Create default pinball machines
python manage.py create_default_machines

# Import legacy maintenance records
python manage.py import_legacy_maintenance_records
