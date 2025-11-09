import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from tickets.models import Game, Maintainer, ProblemReport

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate database with sample maintainers and problem reports for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing maintainers and reports before adding sample data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            report_count = ProblemReport.objects.count()
            maintainer_count = Maintainer.objects.count()
            ProblemReport.objects.all().delete()
            Maintainer.objects.all().delete()
            # Also delete the users (except superusers)
            user_count = User.objects.filter(is_superuser=False).count()
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(
                self.style.WARNING(
                    f'Deleted {user_count} user(s), {maintainer_count} maintainer(s), '
                    f'{report_count} report(s)'
                )
            )

        # Create maintainers
        maintainer_data = [
            {'username': 'form', 'first_name': 'Chris', 'last_name': 'Miller', 'phone': '415-555-0101'},
            {'username': 'thau', 'first_name': 'Dave', 'last_name': 'Thau', 'phone': '415-555-0102'},
            {'username': 'mikek', 'first_name': 'Mike', 'last_name': 'Kuniavsky', 'phone': '415-555-0103'},
            {'username': 'jimh', 'first_name': 'Jim', 'last_name': 'Home', 'phone': '415-555-0104'},
            {'username': 'jcook', 'first_name': 'John', 'last_name': 'Cook', 'phone': '415-555-0105'},
        ]

        maintainers = []
        created_maintainers = 0
        existing_maintainers = 0

        for data in maintainer_data:
            username = data.pop('username')
            first_name = data.pop('first_name')
            last_name = data.pop('last_name')
            phone = data.pop('phone')

            user, user_created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': f'{username}@example.com',
                }
            )

            if user_created:
                user.set_password('test123')
                user.save()

            maintainer, maint_created = Maintainer.objects.get_or_create(
                user=user,
                defaults={'phone': phone}
            )

            maintainers.append(maintainer)

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

        # Get all games to assign reports to
        games = list(Game.objects.filter(is_active=True))
        if not games:
            self.stdout.write(
                self.style.ERROR(
                    'No active games found! Run populate_sample_data first.'
                )
            )
            return

        # Sample problem reports with varying content
        problem_scenarios = [
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck in the castle. Need to open playfield.',
                'reporter_name': 'Sarah Johnson',
                'reporter_contact': 'sarah@email.com',
                'updates': [
                    'Opened playfield and retrieved ball. Checking switch.',
                    'Switch appears to be working. Closed up and tested - all good.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Bill acceptor not working. Inserted $5, no credits given.',
                'reporter_name': 'Mike Davis',
                'reporter_contact': '555-1234',
                'updates': [
                    'Bill stacker was full. Cleared it out.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Display is flickering and hard to read.',
                'reporter_name': 'Anonymous',
                'updates': [
                    'Checked connections - found loose ribbon cable.',
                    'Reseated cable and tested. Display looks good now.',
                    'Monitoring for 24 hours before closing.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball stuck in left ramp. Happens frequently.',
                'reporter_name': 'Tom Wilson',
                'reporter_contact': 'tom.w@email.com',
                'updates': [
                    'Retrieved ball. Ramp appears to have debris buildup.',
                    'Cleaned and waxed ramp. Adjusted angle slightly.',
                    'Tested 20 games - no more sticking. Fixed!',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Coin slot jammed. Quarter stuck inside.',
                'reporter_name': 'Lisa Anderson',
                'updates': [
                    'Removed jammed quarter. Coin mech needs cleaning.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Flippers feel weak on right side.',
                'reporter_name': 'Bob Smith',
                'reporter_contact': '555-5678',
                'updates': [
                    'Measured coil voltage - within spec.',
                    'Replaced flipper rubber - was worn.',
                    'Customer tested and confirmed feels better now.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Multiball started but only 2 balls came out instead of 3.',
                'reporter_name': 'Jessica Lee',
                'updates': []  # No updates yet - still open
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Sound cutting in and out during gameplay.',
                'reporter_name': 'Mark Taylor',
                'reporter_contact': 'mark@email.com',
                'updates': [
                    'Checked amp connections - found cold solder joint.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Machine takes money but immediately goes to tilt.',
                'reporter_name': 'Rachel Green',
                'updates': [
                    'Tilt bob was adjusted too sensitive.',
                    'Recalibrated tilt mechanism per manual.',
                    'Tested - working correctly now.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Left slingshot not firing.',
                'reporter_name': 'Kevin Brown',
                'reporter_contact': '555-9012',
                'updates': [
                    'Switch was bent and not making contact.',
                    'Bent switch back into position. Firing correctly.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck behind drop targets. Lost a ball.',
                'reporter_name': '',  # Anonymous
                'updates': [
                    'Found ball wedged behind target bank.',
                    'Adjusted target spacing to prevent recurrence.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Score not registering properly - stuck at 0.',
                'reporter_name': 'Amy White',
                'updates': []  # Still investigating
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Credit button not working. Can\'t start game.',
                'reporter_name': 'Daniel Martinez',
                'reporter_contact': 'dan.m@email.com',
                'updates': [
                    'Button switch was dirty and corroded.',
                    'Cleaned with contact cleaner. Testing now.',
                    'Working perfectly. Closed.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Magna-save button stuck down.',
                'reporter_name': 'Nicole Garcia',
                'updates': [
                    'Button mechanism had sticky residue (soda?).',
                    'Cleaned thoroughly and lubricated.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball keeps getting stuck in scoop. Very annoying!',
                'reporter_name': 'Paul Rodriguez',
                'reporter_contact': '555-3456',
                'updates': [
                    'Scoop kicker coil weak - measured only 35V.',
                    'Replaced coil sleeve and cleaned.',
                    'Now kicking out reliably at 48V.',
                    'Tested 15 scoops - all successful. Fixed!',
                ]
            },
        ]

        created_reports = 0
        existing_reports = 0

        for scenario in problem_scenarios:
            game = random.choice(games)
            updates_data = scenario.pop('updates')

            # Create the problem report
            report, created = ProblemReport.objects.get_or_create(
                game=game,
                problem_type=scenario['type'],
                problem_text=scenario['text'],
                defaults={
                    'reported_by_name': scenario['reporter_name'],
                    'reported_by_contact': scenario.get('reporter_contact', ''),
                    'device_info': random.choice([
                        'iPhone 13',
                        'Samsung Galaxy S21',
                        'iPad',
                        'Desktop Browser',
                        '',
                    ]),
                    'ip_address': f'192.168.1.{random.randint(10, 250)}',
                }
            )

            if created:
                created_reports += 1

                # Add updates if any
                if updates_data:
                    for i, update_text in enumerate(updates_data):
                        maintainer = random.choice(maintainers)

                        # Last update closes the report
                        if i == len(updates_data) - 1:
                            report.set_status(
                                ProblemReport.STATUS_CLOSED,
                                maintainer,
                                update_text
                            )
                        else:
                            # Just add a note
                            report.add_note(maintainer, update_text)

                    status_emoji = '✓' if report.status == ProblemReport.STATUS_CLOSED else '○'
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'{status_emoji} Created report: {game.name} - '
                            f'{report.get_problem_type_display()} '
                            f'({len(updates_data)} update{"s" if len(updates_data) != 1 else ""})'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'○ Created report: {game.name} - '
                            f'{report.get_problem_type_display()} (open, no updates yet)'
                        )
                    )
            else:
                existing_reports += 1
                self.stdout.write(f'  Already exists: {game.name} report')

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_maintainers} maintainers created, '
                f'{existing_maintainers} already existed'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_reports} reports created, '
                f'{existing_reports} already existed'
            )
        )
