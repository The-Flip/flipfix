"""Import maintainers and admin accounts from CSV."""

import csv
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from the_flip.apps.accounts.models import Maintainer


class Command(BaseCommand):
    help = "Import maintainers from docs/legacy_data/Maintainers.csv"

    CSV_PATH = Path("docs/legacy_data/Maintainers.csv")

    def handle(self, *args, **options):
        if not self.CSV_PATH.exists():
            raise CommandError(f"CSV file not found: {self.CSV_PATH}")

        user_model = get_user_model()
        created_users = 0
        updated_users = 0

        with self.CSV_PATH.open() as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                username = (row.get("Handle") or "").strip()
                if not username:
                    continue
                is_admin = (row.get("Admin") or "").strip().upper() == "TRUE"
                user, created = user_model.objects.get_or_create(username=username)
                user.email = f"{username}@example.com"
                user.is_staff = is_admin
                user.is_superuser = is_admin
                user.set_password("test123")
                user.save()
                Maintainer.objects.get_or_create(user=user)
                if created:
                    created_users += 1
                else:
                    updated_users += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed maintainers. Created {created_users}, updated {updated_users}."
            )
        )
