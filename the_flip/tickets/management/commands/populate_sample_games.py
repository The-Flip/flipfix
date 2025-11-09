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
            # Additional classic DMD games
            {
                "name": "Theatre of Magic",
                "manufacturer": "Bally",
                "year": 1995,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Indiana Jones: The Pinball Adventure",
                "manufacturer": "Williams",
                "year": 1993,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Star Trek: The Next Generation",
                "manufacturer": "Williams",
                "year": 1993,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Scared Stiff",
                "manufacturer": "Bally",
                "year": 1996,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Cirqus Voltaire",
                "manufacturer": "Bally",
                "year": 1997,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Tales of the Arabian Nights",
                "manufacturer": "Williams",
                "year": 1996,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "Terminator 2: Judgment Day",
                "manufacturer": "Williams",
                "year": 1991,
                "type": Game.TYPE_DMD,
            },
            {
                "name": "White Water",
                "manufacturer": "Williams",
                "year": 1993,
                "type": Game.TYPE_DMD,
            },
            # More solid state classics
            {
                "name": "High Speed",
                "manufacturer": "Williams",
                "year": 1986,
                "type": Game.TYPE_SS,
            },
            {
                "name": "F-14 Tomcat",
                "manufacturer": "Williams",
                "year": 1987,
                "type": Game.TYPE_SS,
            },
            {
                "name": "Taxi",
                "manufacturer": "Williams",
                "year": 1988,
                "type": Game.TYPE_SS,
            },
            {
                "name": "Xenon",
                "manufacturer": "Bally",
                "year": 1980,
                "type": Game.TYPE_SS,
            },
            # Modern Stern games
            {
                "name": "Deadpool",
                "manufacturer": "Stern",
                "year": 2018,
                "type": Game.TYPE_LCD,
            },
            {
                "name": "Jurassic Park",
                "manufacturer": "Stern",
                "year": 2019,
                "type": Game.TYPE_LCD,
            },
            {
                "name": "Led Zeppelin",
                "manufacturer": "Stern",
                "year": 2021,
                "type": Game.TYPE_LCD,
            },
            {
                "name": "Stranger Things",
                "manufacturer": "Stern",
                "year": 2020,
                "type": Game.TYPE_LCD,
            },
            # Classic EM games
            {
                "name": "Eight Ball Deluxe",
                "manufacturer": "Bally",
                "year": 1981,
                "type": Game.TYPE_SS,
            },
            {
                "name": "Paragon",
                "manufacturer": "Bally",
                "year": 1979,
                "type": Game.TYPE_SS,
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
