import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from tickets.models import MachineInstance, Maintainer, ProblemReport

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate database with sample problem reports for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing reports before adding sample data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            report_count = ProblemReport.objects.count()
            ProblemReport.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f'Deleted {report_count} report(s)'
                )
            )

        # Get existing maintainers
        maintainers = list(Maintainer.objects.all())

        if not maintainers:
            self.stdout.write(
                self.style.ERROR(
                    'No maintainers found! Please run create_default_maintainers first.'
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Using {len(maintainers)} existing maintainer(s)'
            )
        )
        self.stdout.write('')

        # Get specific machines by name for targeted problem reports
        def get_machine(name):
            try:
                return MachineInstance.objects.get(model__name=name)
            except MachineInstance.DoesNotExist:
                return None

        # Sample problem reports with contextually appropriate content for our specific machines
        # Updates can be:
        # - Simple strings (just add a note)
        # - Dicts with 'text' and 'machine_status': 'good'/'fixing'/'broken' (changes machine status and auto-closes/opens report)
        problem_scenarios = [
            # Baseball - BROKEN status - gooped-up mechanics with multiple repair cycles
            {
                'machine_name': 'Baseball',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': "Mechanics are completely gooped up with old grease and dirt. Machine doesn't work at all.",
                'reporter_name': 'Museum Curator',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Started cleaning process. Removing decades of gunk from mechanical components.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'About 30% through cleaning. Found several broken springs that need replacement.',
                    'Ordered replacement springs from vintage parts supplier.',
                    'Springs arrived. Installing and testing mechanism.',
                    {'text': 'Mechanism working! Ready for display.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                    {'text': 'Spring broke again during demo. These vintage springs are fragile.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    {'text': 'Ordered higher quality reproduction springs. Installing now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                ]
            },
            # Star Trip - left flipper coil melted with full repair cycle ending in reopen
            {
                'machine_name': 'Star Trip',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Left flipper completely dead. No response when button pressed.',
                'reporter_name': 'Tom Wilson',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Opened up the cabinet. Left flipper coil is melted!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    'Investigating why coil melted - checking for electrical issues.',
                    {'text': 'Found short in wiring harness. Replacing coil and fixing short.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Coil replaced, short fixed. Tested 50 games - working perfectly!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                    {'text': 'Flipper died again! Different issue - EOS switch burned out.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    {'text': 'Replacing EOS switch and checking all connections.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                ]
            },
            # Gorgar - transformer and cables
            {
                'machine_name': 'Gorgar',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Game powers on but display is flickering. Boards are disconnected.',
                'reporter_name': 'Sarah Johnson',
                'reporter_contact': '',
                'updates': [
                    'Transformer voltage needs verification. Getting multimeter readings.',
                    'Transformer output looks good. Now adjusting cable connections.',
                    'Boards need to be reinstalled properly. Working on it.',
                ]
            },
            # Star Trek - fixing status
            {
                'machine_name': 'Star Trek',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'MPU board not booting. No display activity.',
                'reporter_name': 'Mike Davis',
                'reporter_contact': '',
                'updates': [
                    'Found corroded battery on MPU board. Battery had leaked.',
                    'Cleaning battery acid damage from traces.',
                    'Ordered replacement MPU board as backup in case damage is too severe.',
                ]
            },
            # Blackout - replace lock, initial machine check
            {
                'machine_name': 'Blackout',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Coin door lock is broken. Need to replace before putting on floor.',
                'reporter_name': 'Lisa Anderson',
                'updates': [
                    {'text': 'Lock ordered. Should arrive in 3-5 days.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Lock installed. Works perfectly.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'Blackout',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Initial machine check before putting on floor.',
                'reporter_name': 'Jim Home',
                'updates': [
                    {'text': 'Running through all switches and lights.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Found one burnt out GI bulb. Replaced.',
                    'All flippers working. Drop targets resetting properly.',
                    {'text': 'Machine checks out. Ready for floor.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Trade Winds - fixing status (early EM) with multiple repair attempts
            {
                'machine_name': 'Trade Winds',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Replay counter not advancing when winning free games.',
                'reporter_name': 'Bob Smith',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Inspecting replay mechanism. Lots of old hardened grease.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Cleaned and re-lubricated replay counter mechanism.',
                    {'text': 'Testing - counter now advances properly!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                    {'text': 'Counter stopped working again. Gear teeth are worn down.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    'Searching for replacement gears. These 1950s parts are hard to find!',
                    {'text': 'Found NOS replacement gear on eBay. Installing and testing.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                ]
            },
            # The Addams Family - popular modern game, occasional issues
            {
                'machine_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball got stuck in the bookcase. Had to open playfield.',
                'reporter_name': 'Jessica Lee',
                'updates': [
                    {'text': 'Retrieved ball from bookcase VUK area.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'VUK kicker seems a bit weak. Adjusting.',
                    {'text': 'Tested 20 times - kicking out reliably now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Thing hand keeps getting stuck in the up position.',
                'reporter_name': 'Mark Taylor',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Motor for Thing hand mechanism needs lubrication.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Lubricated motor and tested. Working smoothly.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                    {'text': 'Thing is stuck up again. Motor may be failing.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    'Ordered replacement motor. Should arrive next week.',
                    {'text': 'New motor installed. Testing thoroughly.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Thing working perfectly with new motor!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                    {'text': 'Motor controller board failed. Thing stuck again!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_BROKEN},
                    {'text': 'Replacing motor controller board. Root cause identified.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                ]
            },
            # Godzilla - modern game with tech issues
            {
                'machine_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Card reader not accepting any cards. Display shows "Card Error".',
                'reporter_name': 'Rachel Green',
                'updates': [
                    {'text': 'Card reader head was dirty from heavy use.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Cleaned with alcohol swabs per manual.',
                    {'text': 'Reading cards successfully now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Building topper not lighting up. Display works fine but topper is dark.',
                'reporter_name': 'Kevin Brown',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Found loose connector on topper LED strip.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Reconnected and secured. All topper lights working.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Teacher's Pet - vintage EM with high rating
            {
                'machine_name': "Teacher's Pet",
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Score reels not advancing correctly on player 2.',
                'reporter_name': 'Amy White',
                'updates': [
                    {'text': 'Player 2 score reel is sticking. Cleaning mechanism.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Found bent wiper on the tens reel. Straightening it out.',
                    {'text': 'All reels advancing smoothly now. Tested 5 full games.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Hokus Pokus - EM with reels
            {
                'machine_name': 'Hokus Pokus',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Chime unit not firing when scoring. Silent during gameplay.',
                'reporter_name': 'Daniel Martinez',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Chime plungers are sticky and not striking.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Cleaned and adjusted all three chime units.',
                    {'text': 'Beautiful chime sounds back! Tested thoroughly.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # The Hulk - early SS
            {
                'machine_name': 'The Hulk',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Display shows random characters. Not readable.',
                'reporter_name': 'Nicole Garcia',
                'updates': [
                    {'text': 'Reseated display ribbon cable.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Display clear and working now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Eight Ball Deluxe Limited Edition - classic SS
            {
                'machine_name': 'Eight Ball Deluxe Limited Edition',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Ball stuck in 8-ball target area.',
                'reporter_name': 'Paul Rodriguez',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Retrieved ball. Target bank spacing was too tight.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Adjusted target spacing. Tested extensively - no more sticking.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # The Getaway - popular DMD era
            {
                'machine_name': 'The Getaway: High Speed II',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Supercharger gear making grinding noise.',
                'reporter_name': 'Steve Chen',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Supercharger gear teeth showing wear.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Ordered replacement supercharger assembly.',
                    'New assembly arrived. Installing now.',
                    {'text': 'Supercharger working smoothly. Sounds great!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Hyperball - unique flipperless game
            {
                'machine_name': 'Hyperball',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Ball launcher feels weak. Barely making it to playfield.',
                'reporter_name': 'Emily White',
                'updates': [
                    {'text': 'Launcher spring tension is low. Adjusting.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Spring replaced and adjusted. Launching perfectly now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Derby Day - vintage EM
            {
                'machine_name': 'Derby Day',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Coin slot jammed. Quarter stuck inside.',
                'reporter_name': 'William Chen',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Removed jammed quarter. Coin mech needs cleaning.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Cleaned and lubricated coin mechanism. Testing now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Roto Pool - vintage EM
            {
                'machine_name': 'Roto Pool',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Rotating pool table mechanism is stuck. Won\'t rotate.',
                'reporter_name': 'Chris Johnson',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Motor for rotating playfield seized up from old grease.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Disassembling mechanism for thorough cleaning.',
                    'Cleaned and re-lubricated with proper light oil.',
                    {'text': 'Playfield rotating smoothly again. Beautiful mechanism!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Ballyhoo - very early PM
            {
                'machine_name': 'Ballyhoo',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Several pins on playfield are loose.',
                'reporter_name': 'Jennifer Mills',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Tightening all loose pins. Some need replacement.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'All pins secure. Playfield in excellent condition for 1932!', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Carom - early EM with unknown status
            {
                'machine_name': 'Carom',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Need full diagnostic. Machine status unknown.',
                'reporter_name': 'Museum Curator',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Starting full inspection of 1937 machine.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Totalizer scoring mechanism appears intact.',
                    'Testing electrical components. Some corrosion on contacts.',
                    'Cleaning contacts and testing scoring.',
                    {'text': 'Machine is operational! Just needed cleaning. Ready for display.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            # Additional varied reports for good machines
            {
                'machine_name': 'Eight Ball Deluxe Limited Edition',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Right flipper feels weak compared to left.',
                'reporter_name': 'Alex Turner',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Measured coil voltage - within spec.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Flipper rubber on right side is worn. Replacing.',
                    {'text': 'New rubber installed. Both flippers feel equal now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'The Addams Family',
                'type': ProblemReport.PROBLEM_NO_CREDITS,
                'text': 'Bill acceptor not giving credits. Ate my $5!',
                'reporter_name': 'Samantha Wright',
                'updates': [
                    {'text': 'Bill stacker was full.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    {'text': 'Emptied bill stacker. Refunded $5. Working now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'Godzilla (Premium)',
                'type': ProblemReport.PROBLEM_OTHER,
                'text': 'Shaker motor runs constantly, even in attract mode.',
                'reporter_name': 'Tyler Brooks',
                'reporter_contact': '',
                'updates': [
                    {'text': 'Shaker relay stuck in closed position.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Replaced relay.',
                    {'text': 'Shaker now activating only during proper game events.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
                ]
            },
            {
                'machine_name': 'The Getaway: High Speed II',
                'type': ProblemReport.PROBLEM_STUCK_BALL,
                'text': 'Multiball lock not holding balls. Balls roll right back out.',
                'reporter_name': 'Patricia Green',
                'updates': [
                    {'text': 'Lock mechanism kicker coil weak.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_FIXING},
                    'Cleaning coil sleeve and plunger.',
                    {'text': 'Tested lock 30 times - holding balls securely now.', 'machine_status': MachineInstance.OPERATIONAL_STATUS_GOOD},
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
            machine = get_machine(scenario.pop('machine_name'))
            if not machine:
                self.stdout.write(
                    self.style.WARNING(f"Machine not found: {scenario.get('machine_name', 'Unknown')}")
                )
                continue

            updates_data = scenario.pop('updates', [])

            # Create the problem report
            report, created = ProblemReport.objects.get_or_create(
                machine=machine,
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

                            # Check if we should change machine status
                            # This automatically handles opening/closing the report
                            if update.get('machine_status'):
                                update_obj = report.set_machine_status(
                                    update['machine_status'],
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
                            f'{status_emoji} Created report: {machine.name} - '
                            f'{report.get_problem_type_display()} '
                            f'({len(updates_data)} update{"s" if len(updates_data) != 1 else ""})'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'○ Created report: {machine.name} - '
                            f'{report.get_problem_type_display()} (open, no updates yet)'
                        )
                    )
            else:
                existing_reports += 1
                self.stdout.write(f'  Already exists: {machine.name} report')

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_reports} reports created, '
                f'{existing_reports} already existed'
            )
        )
