"""Run all legacy importers."""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Import all legacy data."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Importing maintainers..."))
        call_command("import_maintainers")

        self.stdout.write(self.style.NOTICE("Importing machines..."))
        call_command("import_machines")

        self.stdout.write(self.style.NOTICE("Importing maintenance records..."))
        call_command("import_maintenance_records")

        self.stdout.write(self.style.SUCCESS("Legacy import complete."))
