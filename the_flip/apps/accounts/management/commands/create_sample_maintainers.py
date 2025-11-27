"""Create sample maintainer accounts from CSV."""

import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from the_flip.apps.accounts.models import Maintainer


class Command(BaseCommand):
    help = "Create sample maintainers from docs/legacy_data/Maintainers.csv (dev/PR only)"

    CSV_PATH = Path("docs/legacy_data/Maintainers.csv")

    def handle(self, *args, **options):
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
            )

        user_model = get_user_model()

        # Safety check: empty database only
        if user_model.objects.exists():
            raise CommandError(
                "Database already contains users. This command only runs on empty databases."
            )

        if not self.CSV_PATH.exists():
            raise CommandError(f"CSV file not found: {self.CSV_PATH}")

        created_users = 0

        with self.CSV_PATH.open() as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                username = (row.get("Handle") or "").strip()
                if not username:
                    continue
                is_admin = (row.get("Admin") or "").strip().upper() == "TRUE"
                user = user_model.objects.create(
                    username=username,
                    email=f"{username}@example.com",
                    is_staff=is_admin,
                    is_superuser=is_admin,
                )
                user.set_password("test123")
                user.save()
                # Signal auto-creates Maintainer for staff users, but ensure it exists for all
                Maintainer.objects.get_or_create(user=user)
                created_users += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_users} sample maintainers."))
