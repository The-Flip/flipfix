#!/bin/bash

# Script to reset Django migrations for all apps
# This will reset each app's migrations to a single 0001_initial.py
# This is only usable during development when we're wiping the database

set -e  # Exit on error

# Change to project root directory (parent of scripts/)
cd "$(dirname "$0")/.."

echo "=== Resetting migrations ==="
echo ""

# Delete the database FIRST (before deleting migrations)
echo "Deleting database..."
if [ -f db.sqlite3 ]; then
    rm db.sqlite3
    echo "✓ Database deleted"
else
    echo "✓ No database file found (already clean)"
fi
echo ""

# Delete existing migration files
echo "Deleting existing migration files..."
rm -f the_flip/apps/accounts/migrations/0*.py
rm -f the_flip/apps/catalog/migrations/0*.py
rm -f the_flip/apps/maintenance/migrations/0*.py
rm -f the_flip/apps/core/migrations/0*.py
echo "✓ Migration files deleted"
echo ""

# Create fresh initial migrations
echo "Creating new initial migrations..."
python manage.py makemigrations
echo "✓ New initial migrations created"
echo ""

# Run migrations fresh
echo "Running migrations..."
python manage.py migrate
echo "✓ Migrations applied"
echo ""

# Create sample data
echo "Creating sample data..."
python manage.py create_sample_data
echo ""

echo "=== Migration reset complete! ==="
echo ""
echo "You now have fresh 0001_initial.py migrations for all apps."
echo "Sample data has been created."
