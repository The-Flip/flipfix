from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Import all legacy data by running import commands in the correct order"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before importing (passed to sub-commands that support it)",
        )

    def handle(self, *args, **options):
        clear = options.get("clear", False)

        # Commands with their descriptions and whether they support --clear
        commands = [
            ("import_maintainers", "Importing maintainers", False),
            ("import_machines", "Importing machines", False),
            (
                "import_maintenance_records",
                "Importing maintenance records",
                True,
            ),
        ]

        self.stdout.write(self.style.SUCCESS("\n=== Starting Legacy Data Import ===\n"))
        if clear:
            self.stdout.write(self.style.WARNING("Running with --clear flag\n"))

        for command_name, description, supports_clear in commands:
            self.stdout.write(self.style.SUCCESS(f"Step: {description}..."))
            self.stdout.write("")

            try:
                # Pass --clear to commands that support it
                if supports_clear and clear:
                    call_command(command_name, clear=True)
                else:
                    call_command(command_name)
                self.stdout.write(self.style.SUCCESS(f"✓ {description} completed\n"))
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Error during {description}: {str(e)}\n")
                )
                raise

        self.stdout.write(self.style.SUCCESS("=== Legacy Data Import Complete ==="))
