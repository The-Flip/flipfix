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

# Create default admin users
python manage.py create_default_admins

# Create default maintainers
python manage.py create_default_maintainers

# Create default pinball machines
python manage.py create_default_machines

# Create sample problem reports
python manage.py create_sample_problem_reports
