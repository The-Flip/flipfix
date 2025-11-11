from django.core.management.base import BaseCommand
from django.utils import timezone
from tickets.models import Task, LogEntry, MachineInstance, Maintainer
import csv
import os
import re
from datetime import datetime


class Command(BaseCommand):
    help = 'Import legacy maintenance records from CSV files (replaces create_sample_problem_reports)'

    def __init__(self):
        super().__init__()
        # Hardcoded mapping for known machine name mismatches
        self.machine_name_mapping = {
            'RotoPool': 'Roto Pool',
            'Addams Family': 'The Addams Family',
            'The Getaway: High Speed 2': 'The Getaway: High Speed II',
            'Hulk': 'The Incredible Hulk',
        }

    def normalize_name(self, name):
        """Normalize a name by removing capitalization, whitespace, and punctuation"""
        if not name:
            return ''
        # Convert to lowercase, remove extra whitespace, and remove punctuation
        normalized = re.sub(r'[^\w\s]', '', name.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def find_machine(self, machine_name):
        """Find a machine by name using normalized matching strategy"""
        if not machine_name:
            return None

        normalized_search = self.normalize_name(machine_name)

        # First try: direct normalized match
        for machine in MachineInstance.objects.all():
            if self.normalize_name(machine.name) == normalized_search:
                return machine

        # Second try: check hardcoded mapping
        for old_name, new_name in self.machine_name_mapping.items():
            if self.normalize_name(old_name) == normalized_search:
                normalized_new = self.normalize_name(new_name)
                for machine in MachineInstance.objects.all():
                    if self.normalize_name(machine.name) == normalized_new:
                        return machine

        # No match found
        return None

    def find_maintainer(self, maintainer_name):
        """Find a maintainer by name using normalized matching"""
        if not maintainer_name:
            return None

        normalized_search = self.normalize_name(maintainer_name)

        # Try matching against username
        for maintainer in Maintainer.objects.all():
            if self.normalize_name(maintainer.user.username) == normalized_search:
                return maintainer

        # Try matching against first name
        for maintainer in Maintainer.objects.all():
            if self.normalize_name(maintainer.user.first_name) == normalized_search:
                return maintainer

        # Try matching against full name
        for maintainer in Maintainer.objects.all():
            full_name = f"{maintainer.user.first_name} {maintainer.user.last_name}".strip()
            if self.normalize_name(full_name) == normalized_search:
                return maintainer

        return None

    def parse_date(self, date_str):
        """Parse various date formats from CSV"""
        if not date_str:
            return timezone.now()

        # Try common formats
        formats = [
            '%m/%d/%Y %I:%M %p',      # "10/4/2025 6:09 PM"
            '%m/%d/%y, %I:%M %p',     # "1/6/24, 12:00 AM"
            '%m/%d/%Y, %I:%M %p',     # "1/6/2025, 12:00 AM"
            '%m/%d/%y %I:%M %p',      # "1/6/24 12:00 AM"
            '%m/%d/%y',               # "1/6/24"
            '%m/%d/%Y',               # "1/6/2025"
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                # Make timezone-aware
                return timezone.make_aware(dt, timezone.get_current_timezone())
            except ValueError:
                continue

        self.stdout.write(
            self.style.WARNING(f'Could not parse date "{date_str}", using current time')
        )
        return timezone.now()

    def handle(self, *args, **options):
        base_path = os.path.join(
            os.path.dirname(__file__),
            '../../../..',
            'docs/legacy_data'
        )

        # Import Problems as Tasks
        problems_csv = os.path.join(base_path, 'Maintenance - Problems.csv')
        if os.path.exists(problems_csv):
            self.import_problems(problems_csv)
        else:
            self.stdout.write(
                self.style.ERROR(f'Problems CSV not found at {problems_csv}')
            )

        # Import Log Entries
        logs_csv = os.path.join(base_path, 'Maintenance - Log entries.csv')
        if os.path.exists(logs_csv):
            self.import_log_entries(logs_csv)
        else:
            self.stdout.write(
                self.style.ERROR(f'Log entries CSV not found at {logs_csv}')
            )

    def import_problems(self, csv_path):
        """Import problems from Maintenance - Problems.csv as Tasks"""
        self.stdout.write(self.style.SUCCESS('\n=== Importing Problems as Tasks ==='))

        created_count = 0
        error_count = 0

        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                game_name = row.get('Game', '').strip()
                timestamp = row.get('Timestamp', '').strip()
                problem = row.get('Problem', '').strip()
                maintainer_name = row.get('Maintainer', '').strip()
                checked = row.get('Checked / Unchecked', '').strip()

                if not game_name or not problem:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping row with missing game or problem: {row}')
                    )
                    error_count += 1
                    continue

                # Find machine
                machine = self.find_machine(game_name)
                if not machine:
                    available_machines = ', '.join([m.name for m in MachineInstance.objects.all()[:5]])
                    self.stdout.write(
                        self.style.ERROR(
                            f'Machine not found: "{game_name}". Available machines: {available_machines}...'
                        )
                    )
                    error_count += 1
                    continue

                # Find maintainer (optional)
                maintainer = None
                if maintainer_name:
                    maintainer = self.find_maintainer(maintainer_name)
                    if not maintainer:
                        self.stdout.write(
                            self.style.WARNING(f'Maintainer not found: "{maintainer_name}", creating task anyway')
                        )

                # Parse date
                created_at = self.parse_date(timestamp)

                # Determine status based on checked field
                status = 'closed' if checked.lower() == 'checked' else 'open'

                # Create Task with type='problem_report' (these are legacy problem reports)
                task = Task(
                    machine=machine,
                    type='problem_report',
                    problem_type='other',
                    problem_text=problem,
                    status=status,
                )

                # Set reporter info if we have a maintainer
                if maintainer:
                    task.reported_by_name = maintainer.user.get_full_name() or maintainer.user.username

                task.save()

                # Override created_at (set after initial save)
                task.created_at = created_at
                task.save(update_fields=['created_at'])

                created_count += 1
                self.stdout.write(
                    f'✓ Created problem report for {machine.name}: {problem[:50]}...'
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Problems import complete: {created_count} created, {error_count} errors'
            )
        )

    def import_log_entries(self, csv_path):
        """Import log entries from Maintenance - Log entries.csv as standalone LogEntries"""
        self.stdout.write(self.style.SUCCESS('\n=== Importing Log Entries ==='))

        created_count = 0
        error_count = 0

        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            for row in reader:
                machine_name = row.get('Machine', '').strip()
                date_str = row.get('Date', '').strip()
                notes = row.get('Notes', '').strip()
                maintainers_str = row.get('Maintainers', '').strip()

                if not machine_name or not notes:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping row with missing machine or notes: {row}')
                    )
                    error_count += 1
                    continue

                # Find machine
                machine = self.find_machine(machine_name)
                if not machine:
                    available_machines = ', '.join([m.name for m in MachineInstance.objects.all()[:5]])
                    self.stdout.write(
                        self.style.ERROR(
                            f'Machine not found: "{machine_name}". Available machines: {available_machines}...'
                        )
                    )
                    error_count += 1
                    continue

                # Parse date
                created_at = self.parse_date(date_str)

                # Create standalone LogEntry (no task association)
                log_entry = LogEntry(
                    task=None,  # Standalone log entry
                    machine=machine,
                    text=notes,
                )
                log_entry.save()

                # Override created_at (set after initial save)
                log_entry.created_at = created_at
                log_entry.save(update_fields=['created_at'])

                # Parse and associate maintainers (comma-separated)
                if maintainers_str:
                    maintainer_names = [name.strip() for name in maintainers_str.split(',')]
                    maintainers_found = []

                    for maintainer_name in maintainer_names:
                        maintainer = self.find_maintainer(maintainer_name)
                        if maintainer:
                            maintainers_found.append(maintainer)
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Maintainer not found: "{maintainer_name}" for log entry'
                                )
                            )

                    if maintainers_found:
                        log_entry.maintainers.set(maintainers_found)

                created_count += 1
                maintainer_display = ', '.join([m.user.username for m in maintainers_found]) if maintainers_found else 'None'
                self.stdout.write(
                    f'✓ Created log entry for {machine.name} by {maintainer_display}: {notes[:50]}...'
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Log entries import complete: {created_count} created, {error_count} errors'
            )
        )
