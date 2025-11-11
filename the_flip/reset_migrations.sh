#!/bin/bash

# Script to reset Django migrations for all apps
# This will reset migrations to a single 0001_initial.py per app

set -e  # Exit on error

echo "=== Resetting migrations ==="
echo ""

# Delete existing migration files
echo "Deleting existing migration files..."
rm -f tickets/migrations/0*.py
rm -f games/migrations/0*.py
echo "✓ Migration files deleted"
echo ""

# Create fresh initial migrations
echo "Creating new initial migrations..."
python manage.py makemigrations
echo "✓ New initial migrations created"
echo ""

# Delete the database
echo "Deleting database..."
if [ -f db.sqlite3 ]; then
    rm db.sqlite3
    echo "✓ Database deleted"
else
    echo "✓ No database file found (already clean)"
fi
echo ""

# Run migrations fresh
echo "Running migrations..."
python manage.py migrate
echo "✓ Migrations applied"
echo ""

# Import legacy data
echo "Importing legacy data..."
python manage.py import_legacy_data
echo ""

echo "=== Migration reset complete! ==="
echo ""
echo "You now have fresh 0001_initial.py migrations for all apps."
echo "Legacy data has been imported."
