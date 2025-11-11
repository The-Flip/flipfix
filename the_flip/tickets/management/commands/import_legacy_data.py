from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Import all legacy data by running import commands in the correct order'

    def handle(self, *args, **options):
        commands = [
            ('import_legacy_maintainers', 'Importing legacy maintainers'),
            ('create_default_machines', 'Creating default machines'),
            ('import_legacy_maintenance_records', 'Importing legacy maintenance records'),
        ]

        self.stdout.write(self.style.SUCCESS('\n=== Starting Legacy Data Import ===\n'))

        for command_name, description in commands:
            self.stdout.write(self.style.SUCCESS(f'Step: {description}...'))
            self.stdout.write('')

            try:
                call_command(command_name)
                self.stdout.write(self.style.SUCCESS(f'✓ {description} completed\n'))
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error during {description}: {str(e)}\n')
                )
                raise

        self.stdout.write(self.style.SUCCESS('=== Legacy Data Import Complete ==='))
