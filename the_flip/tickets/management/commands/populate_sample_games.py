from django.core.management.base import BaseCommand
from tickets.models import Game


class Command(BaseCommand):
    help = 'Populate database with sample pinball machines for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing games before adding sample data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            count = Game.objects.count()
            Game.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Deleted {count} existing game(s)')
            )

        # Sample pinball machines from museum inventory
        sample_games = [
            {
                "name": "Ballyhoo",
                "manufacturer": "Bally",
                "month": 1,
                "year": 1932,
                "type": Game.TYPE_PM,
                "scoring": "manual",
                "flipper_count": "0",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Carom",
                "manufacturer": "Bally",
                "month": 1,
                "year": 1937,
                "type": Game.TYPE_EM,
                "scoring": "totalizer",
                "flipper_count": "0",
                "status": Game.STATUS_UNKNOWN,
            },
            {
                "name": "Trade Winds",
                "manufacturer": "United",
                "month": 3,
                "year": 1945,
                "type": Game.TYPE_EM,
                "scoring": "lights",
                "status": Game.STATUS_FIXING,
            },
            {
                "name": "Baseball",
                "manufacturer": "Chicago Coin",
                "month": 10,
                "year": 1947,
                "type": Game.TYPE_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "status": Game.STATUS_BROKEN,
            },
            {
                "name": "Derby Day",
                "manufacturer": "Gottlieb",
                "month": 4,
                "year": 1956,
                "type": Game.TYPE_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Roto Pool",
                "manufacturer": "Gottlieb",
                "month": 7,
                "year": 1958,
                "type": Game.TYPE_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Teacher's Pet",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1965,
                "type": Game.TYPE_EM,
                "scoring": "reels",
                "flipper_count": "2",
                "pinside_rating": 8.34,
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Hokus Pokus",
                "manufacturer": "Bally",
                "month": 3,
                "year": 1976,
                "type": Game.TYPE_EM,
                "scoring": "reels",
                "flipper_count": "2",
                "pinside_rating": 7.94,
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Star Trip",
                "manufacturer": "GamePlan",
                "month": 4,
                "year": 1979,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "MPU_1",
                "flipper_count": "2",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Star Trek",
                "manufacturer": "Bally",
                "month": 4,
                "year": 1979,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "Bally MPU AS-2518-35",
                "flipper_count": "2",
                "pinside_rating": 6.76,
                "status": Game.STATUS_FIXING,
            },
            {
                "name": "The Hulk",
                "manufacturer": "Gottlieb",
                "month": 10,
                "year": 1979,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "System 1",
                "flipper_count": "2",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Gorgar",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1979,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "System 6",
                "flipper_count": "2",
                "pinside_rating": 7.56,
                "status": Game.STATUS_FIXING,
            },
            {
                "name": "Blackout",
                "manufacturer": "Williams",
                "month": 6,
                "year": 1980,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "System 6",
                "flipper_count": "2",
                "pinside_rating": 7.70,
                "status": Game.STATUS_FIXING,
            },
            {
                "name": "Hyperball",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1981,
                "type": Game.TYPE_SS,
                "scoring": "alphanumeric",
                "system": "System 7",
                "flipper_count": "0",
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Eight Ball Deluxe Limited Edition",
                "manufacturer": "Bally",
                "month": 8,
                "year": 1982,
                "type": Game.TYPE_SS,
                "scoring": "7-segment",
                "system": "Bally MPU AS-2518-35",
                "flipper_count": "3",
                "pinside_rating": 8.06,
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "The Getaway: High Speed II",
                "manufacturer": "Williams",
                "month": 2,
                "year": 1992,
                "type": Game.TYPE_SS,
                "scoring": "DMD",
                "system": "Fliptronics 2?",
                "flipper_count": "3",
                "pinside_rating": 8.14,
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "The Addams Family",
                "manufacturer": "Williams",
                "month": 3,
                "year": 1992,
                "type": Game.TYPE_SS,
                "scoring": "DMD",
                "system": "Fliptronics 1?",
                "flipper_count": "4",
                "pinside_rating": 8.56,
                "status": Game.STATUS_GOOD,
            },
            {
                "name": "Godzilla (Premium)",
                "manufacturer": "Stern",
                "month": 10,
                "year": 2021,
                "type": Game.TYPE_SS,
                "scoring": "video",
                "system": "Spike 2",
                "flipper_count": "3",
                "pinside_rating": 9.19,
                "status": Game.STATUS_GOOD,
            },
        ]

        created_count = 0
        existing_count = 0

        for game_data in sample_games:
            game, created = Game.objects.get_or_create(
                name=game_data["name"],
                defaults=game_data
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Created: {game.name} ({game.year} {game.manufacturer})')
                )
            else:
                existing_count += 1
                self.stdout.write(
                    f'  Already exists: {game.name}'
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {created_count} created, {existing_count} already existed'
            )
        )
