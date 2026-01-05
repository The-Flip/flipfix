"""Create sample accounts."""

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from the_flip.apps.accounts.models import Maintainer


class Command(BaseCommand):
    help = "Create sample accounts from docs/sample_data/accounts.json (dev/PR environments only, not prod)"

    data_path = Path("docs/sample_data/records/accounts.json")

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

        if not self.data_path.exists():
            raise CommandError(f"Data file not found: {self.data_path}")

        with self.data_path.open() as fh:
            data = json.load(fh)

        self.stdout.write(self.style.SUCCESS("\nCreating sample accounts..."))

        # Create admin users
        admin_usernames = []
        for admin_data in data.get("admins", []):
            user = self._create_user(user_model, admin_data, is_admin=True)
            if user:
                admin_usernames.append(user.username)

        # Create regular maintainer users
        maintainer_usernames = []
        for maintainer_data in data.get("maintainers", []):
            user = self._create_user(user_model, maintainer_data, is_admin=False)
            if user:
                maintainer_usernames.append(user.username)

        # Create terminal users (for kiosk mode)
        terminal_usernames = []
        for terminal_data in data.get("terminals", []):
            user = self._create_terminal_user(user_model, terminal_data)
            if user:
                terminal_usernames.append(user.username)

        # Summary output
        if admin_usernames:
            self.stdout.write(
                f"  Created {len(admin_usernames)} admins: {', '.join(admin_usernames)}"
            )
        if maintainer_usernames:
            self.stdout.write(
                f"  Created {len(maintainer_usernames)} maintainer accounts: {', '.join(maintainer_usernames)}"
            )
        if terminal_usernames:
            self.stdout.write(
                f"  Created {len(terminal_usernames)} shared terminal accounts: {', '.join(terminal_usernames)}"
            )

        total = len(admin_usernames) + len(maintainer_usernames) + len(terminal_usernames)
        self.stdout.write(self.style.SUCCESS(f"Created {total} sample accounts."))

    def _create_user(self, user_model, data: dict, *, is_admin: bool):
        """Create a user (admin or maintainer) from JSON data."""
        username = data.get("username", "").strip()
        if not username:
            return None

        first_name = data.get("first_name", "").strip()
        last_name = data.get("last_name", "").strip()
        email = data.get("email", "").strip() or f"{username}@example.com"

        user = user_model.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_admin,
            is_superuser=is_admin,
        )
        user.set_password("test123")
        user.save()

        # Signal auto-creates Maintainer for staff users, but ensure it exists for all
        Maintainer.objects.get_or_create(user=user)

        return user

    def _create_terminal_user(self, user_model, data: dict):
        """Create a terminal user for kiosk mode."""
        username = data.get("username", "").strip()
        if not username:
            return None

        display_name = data.get("display_name", "").strip()

        user = user_model.objects.create(
            username=username,
            email=f"{username}@terminals.local",
            first_name=display_name,
        )
        user.set_password("test123")
        user.save()

        # Terminals don't need Maintainer profiles

        return user
