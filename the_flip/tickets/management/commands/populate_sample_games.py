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

        # Sample pinball machines - mix of classic and modern games
        sample_games = [
            # Classic DMD era games
            {
                "name": "Medieval Madness",
                "manufacturer": "Williams",
                "year": 1997,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "The Addams Family",
                "manufacturer": "Bally",
                "year": 1992,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Attack from Mars",
                "manufacturer": "Bally",
                "year": 1995,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Twilight Zone",
                "manufacturer": "Bally",
                "year": 1993,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Monster Bash",
                "manufacturer": "Williams",
                "year": 1998,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Funhouse",
                "manufacturer": "Williams",
                "year": 1990,
                "type": Game.TYPE_DMD,
            },
            # Solid State era
            {
                "name": "Black Knight",
                "manufacturer": "Williams",
                "year": 1980,
                "type": Game.TYPE_SS,
            },
            {
                "name": "Gorgar",
                "manufacturer": "Williams",
                "year": 1979,
                "type": Game.TYPE_SS,
            },
            # Electro-Mechanical era
            {
                "name": "Fireball",
                "manufacturer": "Bally",
                "year": 1972,
                "type": Game.TYPE_EM,
            },
            {
                "name": "Big Shot",
                "manufacturer": "Gottlieb",
                "year": 1973,
                "type": Game.TYPE_EM,
            },
            # Modern LCD games
            {
                "name": "The Mandalorian",
                "manufacturer": "Stern",
                "year": 2021,
                "type": Game.TYPE_LCD,
            },
            {
                "name": "Godzilla",
                "manufacturer": "Stern",
                "year": 2021,
                "type": Game.TYPE_LCD,
            },
            # Add one that's inactive (under maintenance)
            {
                "name": "Creature from the Black Lagoon",
                "manufacturer": "Bally",
                "year": 1992,
                "type": Game.TYPE_DMD,
                "is_active": False,
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
