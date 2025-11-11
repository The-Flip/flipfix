from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tickets.models import Maintainer

User = get_user_model()


class Command(BaseCommand):
    help = 'Create default maintainers for the system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing maintainers before adding default data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            maintainer_count = Maintainer.objects.count()
            # Also delete the users (except superusers)
            user_count = User.objects.filter(is_superuser=False).count()
            Maintainer.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(
                self.style.WARNING(
                    f'Deleted {user_count} user(s), {maintainer_count} maintainer(s)'
                )
            )

        # Create maintainers based on the legacy data
        # Note: William is excluded as they are already an admin
        maintainer_data = [
            {'username': 'ken', 'first_name': 'Ken', 'last_name': ''},
            {'username': 'caleb', 'first_name': 'Caleb', 'last_name': ''},
            {'username': 'brian', 'first_name': 'Brian', 'last_name': ''},
            {'username': 'diana', 'first_name': 'Diana', 'last_name': ''},
            {'username': 'reba', 'first_name': 'Reba', 'last_name': ''},
            {'username': 'nick', 'first_name': 'Nick', 'last_name': ''},
            {'username': 'jackie', 'first_name': 'Jackie', 'last_name': ''},
            {'username': 'laura', 'first_name': 'Laura', 'last_name': ''},
            {'username': 'mauricio', 'first_name': 'Mauricio', 'last_name': ''},
        ]

        created_maintainers = 0
        existing_maintainers = 0

        for data in maintainer_data:
            username = data.pop('username')
            first_name = data.pop('first_name')
            last_name = data.pop('last_name')

            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': '',
                }
            )

            if user_created:
                user.set_password('test123')
                user.save()

            maintainer, maint_created = Maintainer.objects.get_or_create(
                user=user,
                defaults={'phone': ''}
            )

            if maint_created:
                created_maintainers += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created maintainer: {maintainer} ({username})'
                    )
                )
            else:
                existing_maintainers += 1
                self.stdout.write(f'  Already exists: {maintainer}')

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_maintainers} maintainers created, '
                f'{existing_maintainers} already existed'
            )
        )
