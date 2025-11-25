"""Run all sample data creators."""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create all sample data (dev/PR only)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Creating sample maintainers..."))
        call_command("create_sample_maintainers")

        self.stdout.write(self.style.NOTICE("Creating sample machines..."))
        call_command("create_sample_machines")

        self.stdout.write(self.style.NOTICE("Creating sample maintenance records..."))
        call_command("create_sample_maintenance_records")

        self.stdout.write(self.style.SUCCESS("Sample data creation complete."))
