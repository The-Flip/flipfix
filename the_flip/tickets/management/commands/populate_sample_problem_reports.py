import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
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
        # Updates can be:
        # - Simple strings (just add a note)
        # - Dicts with 'text' and 'close': True (closes the report)
        # - Dicts with 'text' and 'reopen': True (reopens a closed report)
        problem_scenarios = [
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck in the castle. Need to open playfield.',
                'reporter_name': 'Sarah Johnson',
                'reporter_contact': 'sarah@email.com',
                'updates': [
                    'Opened playfield and retrieved ball. Checking switch.',
                    {'text': 'Switch appears to be working. Closed up and tested - all good.', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Bill acceptor not working. Inserted $5, no credits given.',
                'reporter_name': 'Mike Davis',
                'reporter_contact': '555-1234',
                'updates': [
                    {'text': 'Bill stacker was full. Cleared it out.', 'close': True},
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
                    {'text': 'Tested 20 games - no more sticking. Fixed!', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Coin slot jammed. Quarter stuck inside.',
                'reporter_name': 'Lisa Anderson',
                'updates': [
                    'Removed jammed quarter. Coin mech needs cleaning.',
                    {'text': 'Cleaned and lubricated coin mechanism. Testing now.', 'close': True},
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
                    {'text': 'Customer tested and confirmed feels better now.', 'close': True},
                    {'text': 'Customer reports flipper is weak again after a few games. Investigating further.', 'reopen': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Multiball started but only 2 balls came out instead of 3.',
                'reporter_name': 'Jessica Lee',
                'updates': [
                    'Checked ball trough - found one ball stuck.',
                    'Freed stuck ball and tested multiball 5 times - works now.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Sound cutting in and out during gameplay.',
                'reporter_name': 'Mark Taylor',
                'reporter_contact': 'mark@email.com',
                'updates': [
                    'Checked amp connections - found cold solder joint.',
                    'Resoldered connection and tested.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Machine takes money but immediately goes to tilt.',
                'reporter_name': 'Rachel Green',
                'updates': [
                    'Tilt bob was adjusted too sensitive.',
                    'Recalibrated tilt mechanism per manual.',
                    {'text': 'Tested - working correctly now.', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Left slingshot not firing.',
                'reporter_name': 'Kevin Brown',
                'reporter_contact': '555-9012',
                'updates': [
                    'Switch was bent and not making contact.',
                    {'text': 'Bent switch back into position. Firing correctly.', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck behind drop targets. Lost a ball.',
                'reporter_name': '',  # Anonymous
                'updates': [
                    'Found ball wedged behind target bank.',
                    {'text': 'Adjusted target spacing to prevent recurrence.', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Score not registering properly - stuck at 0.',
                'reporter_name': 'Amy White',
                'updates': [
                    'Checked display connections - all good.',
                    'Reviewing board for cold solder joints.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Credit button not working. Can\'t start game.',
                'reporter_name': 'Daniel Martinez',
                'reporter_contact': 'dan.m@email.com',
                'updates': [
                    'Button switch was dirty and corroded.',
                    'Cleaned with contact cleaner. Testing now.',
                    {'text': 'Working perfectly. Closed.', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Magna-save button stuck down.',
                'reporter_name': 'Nicole Garcia',
                'updates': [
                    'Button mechanism had sticky residue (soda?).',
                    {'text': 'Cleaned thoroughly and lubricated.', 'close': True},
                    {'text': 'Button is sticking again. Need to replace the mechanism entirely.', 'reopen': True},
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
                    {'text': 'Tested 15 scoops - all successful. Fixed!', 'close': True},
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Right flipper making grinding noise when pressed.',
                'reporter_name': 'Steve Chen',
                'reporter_contact': 'steve.c@email.com',
                'updates': [
                    'Inspected flipper mechanism - found worn bushing.',
                    'Ordered replacement parts.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Accepts quarters but only gives 1 credit instead of 2.',
                'reporter_name': 'Maria Lopez',
                'updates': [
                    'Checked coin switch settings in service menu.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball drained but game didn\'t register it. Still waiting for ball.',
                'reporter_name': '',
                'updates': []
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'All playfield lights flickering intermittently.',
                'reporter_name': 'Chris Johnson',
                'reporter_contact': '555-7890',
                'updates': [
                    'Checked power supply - voltage is unstable.',
                    'Testing with spare power supply to isolate issue.',
                ]
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Ball launcher feels very weak. Barely makes it up the ramp.',
                'reporter_name': 'Emily White',
                'updates': []
            },
            {
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Machine stuck in free play mode. Won\'t accept credits.',
                'reporter_name': 'Robert King',
                'reporter_contact': 'r.king@email.com',
                'updates': []
            },
            {
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Top right bumper not firing at all.',
                'reporter_name': 'Jennifer Mills',
                'reporter_contact': '555-4321',
                'updates': [
                    'Coil appears dead. Checking for power at connector.',
                ]
            },
        ]

        created_reports = 0
        existing_reports = 0

        # Start with reports from 30 days ago and work forward
        now = timezone.now()
        base_time = now - timedelta(days=30)

        for i, scenario in enumerate(problem_scenarios):
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

                # Set created_at to spread reports over the last 30 days
                # Each report is roughly 1-2 days apart with some randomness
                days_offset = i * 1.5 + random.uniform(-0.5, 0.5)
                report.created_at = base_time + timedelta(days=days_offset)
                report.save(update_fields=['created_at'])

                # Add updates if any
                if updates_data:
                    # Start updates a few hours to a day after the report was created
                    update_time = report.created_at + timedelta(hours=random.uniform(2, 24))

                    for update in updates_data:
                        maintainer = random.choice(maintainers)
                        update_obj = None

                        # Update can be a string or a dict
                        if isinstance(update, str):
                            # Simple note
                            update_obj = report.add_note(maintainer, update)
                        elif isinstance(update, dict):
                            text = update['text']
                            if update.get('close'):
                                # Close the report
                                update_obj = report.set_status(
                                    ProblemReport.STATUS_CLOSED,
                                    maintainer,
                                    text
                                )
                            elif update.get('reopen'):
                                # Reopen the report
                                update_obj = report.set_status(
                                    ProblemReport.STATUS_OPEN,
                                    maintainer,
                                    text
                                )
                            else:
                                # Just a note
                                update_obj = report.add_note(maintainer, text)

                        # Set the update's created_at timestamp
                        if update_obj:
                            update_obj.created_at = update_time
                            update_obj.save(update_fields=['created_at'])
                            # Next update is a few hours to a day later
                            update_time += timedelta(hours=random.uniform(3, 24))

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
