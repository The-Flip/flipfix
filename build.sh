#!/usr/bin/env bash
# Build script for deployment on hosting providers like Render.com and Railway

# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Create media directory if it doesn't exist
mkdir -p media

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input

# Import legacy maintainers and make some of them admins
python manage.py import_maintainers

# Import legacy pinball machines
python manage.py import_machines

# Import legacy maintenance records
python manage.py import_maintenance_records
