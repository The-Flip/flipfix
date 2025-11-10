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

        # Get specific games by name for targeted problem reports
        def get_game(name):
            try:
                return Game.objects.get(name=name)
            except Game.DoesNotExist:
                return None

        # Sample problem reports with contextually appropriate content for our specific machines
        # Updates can be:
        # - Simple strings (just add a note)
        # - Dicts with 'text' and 'game_status': 'good'/'fixing'/'broken' (changes game status and auto-closes/opens report)
        problem_scenarios = [
            # Baseball - BROKEN status - gooped-up mechanics with multiple repair cycles
            {
                'game_name': 'Baseball',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': "Mechanics are completely gooped up with old grease and dirt. Machine doesn't work at all.",
                'reporter_name': 'Museum Curator',
                'reporter_contact': 'curator@museum.org',
                'updates': [
                    {'text': 'Started cleaning process. Removing decades of gunk from mechanical components.', 'game_status': Game.STATUS_FIXING},
                    'About 30% through cleaning. Found several broken springs that need replacement.',
                    'Ordered replacement springs from vintage parts supplier.',
                    'Springs arrived. Installing and testing mechanism.',
                    {'text': 'Mechanism working! Ready for display.', 'game_status': Game.STATUS_GOOD},
                    {'text': 'Spring broke again during demo. These vintage springs are fragile.', 'game_status': Game.STATUS_BROKEN},
                    {'text': 'Ordered higher quality reproduction springs. Installing now.', 'game_status': Game.STATUS_FIXING},
                ]
            },
            # Star Trip - left flipper coil melted with full repair cycle ending in reopen
            {
                'game_name': 'Star Trip',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Left flipper completely dead. No response when button pressed.',
                'reporter_name': 'Tom Wilson',
                'reporter_contact': 'tom.w@email.com',
                'updates': [
                    {'text': 'Opened up the cabinet. Left flipper coil is melted!', 'game_status': Game.STATUS_BROKEN},
                    'Investigating why coil melted - checking for electrical issues.',
                    {'text': 'Found short in wiring harness. Replacing coil and fixing short.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Coil replaced, short fixed. Tested 50 games - working perfectly!', 'game_status': Game.STATUS_GOOD},
                    {'text': 'Flipper died again! Different issue - EOS switch burned out.', 'game_status': Game.STATUS_BROKEN},
                    {'text': 'Replacing EOS switch and checking all connections.', 'game_status': Game.STATUS_FIXING},
                ]
            },
            # Gorgar - transformer and cables
            {
                'game_name': 'Gorgar',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Game powers on but display is flickering. Boards are disconnected.',
                'reporter_name': 'Sarah Johnson',
                'reporter_contact': 'sarah@email.com',
                'updates': [
                    'Transformer voltage needs verification. Getting multimeter readings.',
                    'Transformer output looks good. Now adjusting cable connections.',
                    'Boards need to be reinstalled properly. Working on it.',
                ]
            },
            # Star Trek - fixing status
            {
                'game_name': 'Star Trek',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'MPU board not booting. No display activity.',
                'reporter_name': 'Mike Davis',
                'reporter_contact': '555-1234',
                'updates': [
                    'Found corroded battery on MPU board. Battery had leaked.',
                    'Cleaning battery acid damage from traces.',
                    'Ordered replacement MPU board as backup in case damage is too severe.',
                ]
            },
            # Blackout - replace lock, initial machine check
            {
                'game_name': 'Blackout',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Coin door lock is broken. Need to replace before putting on floor.',
                'reporter_name': 'Lisa Anderson',
                'updates': [
                    {'text': 'Lock ordered. Should arrive in 3-5 days.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Lock installed. Works perfectly.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'Blackout',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Initial machine check before putting on floor.',
                'reporter_name': 'Jim Home',
                'updates': [
                    {'text': 'Running through all switches and lights.', 'game_status': Game.STATUS_FIXING},
                    'Found one burnt out GI bulb. Replaced.',
                    'All flippers working. Drop targets resetting properly.',
                    {'text': 'Machine checks out. Ready for floor.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Trade Winds - fixing status (early EM) with multiple repair attempts
            {
                'game_name': 'Trade Winds',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Replay counter not advancing when winning free games.',
                'reporter_name': 'Bob Smith',
                'reporter_contact': '555-5678',
                'updates': [
                    {'text': 'Inspecting replay mechanism. Lots of old hardened grease.', 'game_status': Game.STATUS_FIXING},
                    'Cleaned and re-lubricated replay counter mechanism.',
                    {'text': 'Testing - counter now advances properly!', 'game_status': Game.STATUS_GOOD},
                    {'text': 'Counter stopped working again. Gear teeth are worn down.', 'game_status': Game.STATUS_BROKEN},
                    'Searching for replacement gears. These 1950s parts are hard to find!',
                    {'text': 'Found NOS replacement gear on eBay. Installing and testing.', 'game_status': Game.STATUS_FIXING},
                ]
            },
            # The Addams Family - popular modern game, occasional issues
            {
                'game_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck in the bookcase. Had to open playfield.',
                'reporter_name': 'Jessica Lee',
                'updates': [
                    {'text': 'Retrieved ball from bookcase VUK area.', 'game_status': Game.STATUS_FIXING},
                    'VUK kicker seems a bit weak. Adjusting.',
                    {'text': 'Tested 20 times - kicking out reliably now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Thing hand keeps getting stuck in the up position.',
                'reporter_name': 'Mark Taylor',
                'reporter_contact': 'mark@email.com',
                'updates': [
                    {'text': 'Motor for Thing hand mechanism needs lubrication.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Lubricated motor and tested. Working smoothly.', 'game_status': Game.STATUS_GOOD},
                    {'text': 'Thing is stuck up again. Motor may be failing.', 'game_status': Game.STATUS_BROKEN},
                    'Ordered replacement motor. Should arrive next week.',
                    {'text': 'New motor installed. Testing thoroughly.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Thing working perfectly with new motor!', 'game_status': Game.STATUS_GOOD},
                    {'text': 'Motor controller board failed. Thing stuck again!', 'game_status': Game.STATUS_BROKEN},
                    {'text': 'Replacing motor controller board. Root cause identified.', 'game_status': Game.STATUS_FIXING},
                ]
            },
            # Godzilla - modern game with tech issues
            {
                'game_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Card reader not accepting any cards. Display shows "Card Error".',
                'reporter_name': 'Rachel Green',
                'updates': [
                    {'text': 'Card reader head was dirty from heavy use.', 'game_status': Game.STATUS_FIXING},
                    'Cleaned with alcohol swabs per manual.',
                    {'text': 'Reading cards successfully now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Building topper not lighting up. Display works fine but topper is dark.',
                'reporter_name': 'Kevin Brown',
                'reporter_contact': '555-9012',
                'updates': [
                    {'text': 'Found loose connector on topper LED strip.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Reconnected and secured. All topper lights working.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Teacher's Pet - vintage EM with high rating
            {
                'game_name': "Teacher's Pet",
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Score reels not advancing correctly on player 2.',
                'reporter_name': 'Amy White',
                'updates': [
                    {'text': 'Player 2 score reel is sticking. Cleaning mechanism.', 'game_status': Game.STATUS_FIXING},
                    'Found bent wiper on the tens reel. Straightening it out.',
                    {'text': 'All reels advancing smoothly now. Tested 5 full games.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Hokus Pokus - EM with reels
            {
                'game_name': 'Hokus Pokus',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Chime unit not firing when scoring. Silent during gameplay.',
                'reporter_name': 'Daniel Martinez',
                'reporter_contact': 'dan.m@email.com',
                'updates': [
                    {'text': 'Chime plungers are sticky and not striking.', 'game_status': Game.STATUS_FIXING},
                    'Cleaned and adjusted all three chime units.',
                    {'text': 'Beautiful chime sounds back! Tested thoroughly.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # The Hulk - early SS
            {
                'game_name': 'The Hulk',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Display shows random characters. Not readable.',
                'reporter_name': 'Nicole Garcia',
                'updates': [
                    {'text': 'Reseated display ribbon cable.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Display clear and working now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Eight Ball Deluxe Limited Edition - classic SS
            {
                'game_name': 'Eight Ball Deluxe Limited Edition',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball stuck in 8-ball target area.',
                'reporter_name': 'Paul Rodriguez',
                'reporter_contact': '555-3456',
                'updates': [
                    {'text': 'Retrieved ball. Target bank spacing was too tight.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Adjusted target spacing. Tested extensively - no more sticking.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # The Getaway - popular DMD era
            {
                'game_name': 'The Getaway: High Speed II',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Supercharger gear making grinding noise.',
                'reporter_name': 'Steve Chen',
                'reporter_contact': 'steve.c@email.com',
                'updates': [
                    {'text': 'Supercharger gear teeth showing wear.', 'game_status': Game.STATUS_FIXING},
                    'Ordered replacement supercharger assembly.',
                    'New assembly arrived. Installing now.',
                    {'text': 'Supercharger working smoothly. Sounds great!', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Hyperball - unique flipperless game
            {
                'game_name': 'Hyperball',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Ball launcher feels weak. Barely making it to playfield.',
                'reporter_name': 'Emily White',
                'updates': [
                    {'text': 'Launcher spring tension is low. Adjusting.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Spring replaced and adjusted. Launching perfectly now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Derby Day - vintage EM
            {
                'game_name': 'Derby Day',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Coin slot jammed. Quarter stuck inside.',
                'reporter_name': 'William Chen',
                'reporter_contact': 'w.chen@email.com',
                'updates': [
                    {'text': 'Removed jammed quarter. Coin mech needs cleaning.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Cleaned and lubricated coin mechanism. Testing now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Roto Pool - vintage EM
            {
                'game_name': 'Roto Pool',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Rotating pool table mechanism is stuck. Won\'t rotate.',
                'reporter_name': 'Chris Johnson',
                'reporter_contact': '555-7890',
                'updates': [
                    {'text': 'Motor for rotating playfield seized up from old grease.', 'game_status': Game.STATUS_FIXING},
                    'Disassembling mechanism for thorough cleaning.',
                    'Cleaned and re-lubricated with proper light oil.',
                    {'text': 'Playfield rotating smoothly again. Beautiful mechanism!', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Ballyhoo - very early PM
            {
                'game_name': 'Ballyhoo',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Several pins on playfield are loose.',
                'reporter_name': 'Jennifer Mills',
                'reporter_contact': '555-4321',
                'updates': [
                    {'text': 'Tightening all loose pins. Some need replacement.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'All pins secure. Playfield in excellent condition for 1932!', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Carom - early EM with unknown status
            {
                'game_name': 'Carom',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Need full diagnostic. Machine status unknown.',
                'reporter_name': 'Museum Curator',
                'reporter_contact': 'curator@museum.org',
                'updates': [
                    {'text': 'Starting full inspection of 1937 machine.', 'game_status': Game.STATUS_FIXING},
                    'Totalizer scoring mechanism appears intact.',
                    'Testing electrical components. Some corrosion on contacts.',
                    'Cleaning contacts and testing scoring.',
                    {'text': 'Machine is operational! Just needed cleaning. Ready for display.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            # Additional varied reports for good machines
            {
                'game_name': 'Eight Ball Deluxe Limited Edition',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Right flipper feels weak compared to left.',
                'reporter_name': 'Alex Turner',
                'reporter_contact': 'alex.t@email.com',
                'updates': [
                    {'text': 'Measured coil voltage - within spec.', 'game_status': Game.STATUS_FIXING},
                    'Flipper rubber on right side is worn. Replacing.',
                    {'text': 'New rubber installed. Both flippers feel equal now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Bill acceptor not giving credits. Ate my $5!',
                'reporter_name': 'Samantha Wright',
                'updates': [
                    {'text': 'Bill stacker was full.', 'game_status': Game.STATUS_FIXING},
                    {'text': 'Emptied bill stacker. Refunded $5. Working now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Shaker motor runs constantly, even in attract mode.',
                'reporter_name': 'Tyler Brooks',
                'reporter_contact': '555-2468',
                'updates': [
                    {'text': 'Shaker relay stuck in closed position.', 'game_status': Game.STATUS_FIXING},
                    'Replaced relay.',
                    {'text': 'Shaker now activating only during proper game events.', 'game_status': Game.STATUS_GOOD},
                ]
            },
            {
                'game_name': 'The Getaway: High Speed II',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Multiball lock not holding balls. Balls roll right back out.',
                'reporter_name': 'Patricia Green',
                'updates': [
                    {'text': 'Lock mechanism kicker coil weak.', 'game_status': Game.STATUS_FIXING},
                    'Cleaning coil sleeve and plunger.',
                    {'text': 'Tested lock 30 times - holding balls securely now.', 'game_status': Game.STATUS_GOOD},
                ]
            },
        ]

        created_reports = 0
        existing_reports = 0

        # Use a fixed "now" to ensure all timestamps are in the past
        # Set to 1 hour ago to give a buffer
        now = timezone.now() - timedelta(hours=1)
        # Start with reports from 30 days before that
        base_time = now - timedelta(days=30)

        for i, scenario in enumerate(problem_scenarios):
            game = get_game(scenario.pop('game_name'))
            if not game:
                self.stdout.write(
                    self.style.WARNING(f"Game not found: {scenario.get('game_name', 'Unknown')}")
                )
                continue

            updates_data = scenario.pop('updates', [])

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

                            # Check if we should change game status
                            # This automatically handles opening/closing the report
                            if update.get('game_status'):
                                update_obj = report.set_game_status(
                                    update['game_status'],
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
