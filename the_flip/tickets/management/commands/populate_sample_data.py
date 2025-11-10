from django.core.management.base import BaseCommand
from tickets.models import MachineModel, MachineInstance


class Command(BaseCommand):
    help = 'Populate database with sample pinball machine data for development'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before adding sample data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            instance_count = MachineInstance.objects.count()
            model_count = MachineModel.objects.count()
            MachineInstance.objects.all().delete()
            MachineModel.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f'Deleted {instance_count} machine instance(s) and {model_count} machine model(s)'
                )
            )

        # Sample machine models from museum inventory
        # Data extracted from populate_sample_games.py and legacy CSV
        sample_models = [
            {
                "name": "Ballyhoo",
                "manufacturer": "Bally",
                "month": 1,
                "year": 1932,
                "era": MachineModel.ERA_PM,
                "scoring": "manual",
                "flipper_count": "0",
                "ipdb_id": 4817,
            },
            {
                "name": "Carom",
                "manufacturer": "Bally",
                "month": 1,
                "year": 1937,
                "era": MachineModel.ERA_EM,
                "scoring": "totalizer",
                "flipper_count": "0",
                "ipdb_id": 458,
            },
            {
                "name": "Trade Winds",
                "manufacturer": "United",
                "month": 3,
                "year": 1945,
                "era": MachineModel.ERA_EM,
                "scoring": "lights",
                "ipdb_id": 2620,
            },
            {
                "name": "Baseball",
                "manufacturer": "Chicago Coin",
                "month": 10,
                "year": 1947,
                "era": MachineModel.ERA_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "ipdb_id": 189,
            },
            {
                "name": "Derby Day",
                "manufacturer": "Gottlieb",
                "month": 4,
                "year": 1956,
                "era": MachineModel.ERA_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "ipdb_id": 664,
            },
            {
                "name": "Roto Pool",
                "manufacturer": "Gottlieb",
                "month": 7,
                "year": 1958,
                "era": MachineModel.ERA_EM,
                "scoring": "lights",
                "flipper_count": "2",
                "ipdb_id": 2022,
            },
            {
                "name": "Teacher's Pet",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1965,
                "era": MachineModel.ERA_EM,
                "scoring": "reels",
                "flipper_count": "2",
                "pinside_rating": 8.34,
                "ipdb_id": 2506,
            },
            {
                "name": "Hokus Pokus",
                "manufacturer": "Bally",
                "month": 3,
                "year": 1976,
                "era": MachineModel.ERA_EM,
                "scoring": "reels",
                "flipper_count": "2",
                "pinside_rating": 7.94,
                "ipdb_id": 1206,
            },
            {
                "name": "Star Trip",
                "manufacturer": "GamePlan",
                "month": 4,
                "year": 1979,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "MPU_1",
                "flipper_count": "2",
                "ipdb_id": 3605,
            },
            {
                "name": "Star Trek",
                "manufacturer": "Bally",
                "month": 4,
                "year": 1979,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "Bally MPU AS-2518-35",
                "flipper_count": "2",
                "pinside_rating": 6.76,
                "ipdb_id": 2355,
            },
            {
                "name": "The Hulk",
                "manufacturer": "Gottlieb",
                "month": 10,
                "year": 1979,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "System 1",
                "flipper_count": "2",
                "ipdb_id": 1266,
            },
            {
                "name": "Gorgar",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1979,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "System 6",
                "flipper_count": "2",
                "pinside_rating": 7.56,
                "ipdb_id": 1062,
            },
            {
                "name": "Blackout",
                "manufacturer": "Williams",
                "month": 6,
                "year": 1980,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "System 6",
                "flipper_count": "2",
                "pinside_rating": 7.70,
                "ipdb_id": 317,
            },
            {
                "name": "Hyperball",
                "manufacturer": "Williams",
                "month": 12,
                "year": 1981,
                "era": MachineModel.ERA_SS,
                "scoring": "alphanumeric",
                "system": "System 7",
                "flipper_count": "0",
                "ipdb_id": 3169,
            },
            {
                "name": "Eight Ball Deluxe Limited Edition",
                "manufacturer": "Bally",
                "month": 8,
                "year": 1982,
                "era": MachineModel.ERA_SS,
                "scoring": "7-segment",
                "system": "Bally MPU AS-2518-35",
                "flipper_count": "3",
                "pinside_rating": 8.06,
                "ipdb_id": 763,
            },
            {
                "name": "The Getaway: High Speed II",
                "manufacturer": "Williams",
                "month": 2,
                "year": 1992,
                "era": MachineModel.ERA_SS,
                "scoring": "DMD",
                "system": "Fliptronics 2?",
                "flipper_count": "3",
                "pinside_rating": 8.14,
                "ipdb_id": 1000,
            },
            {
                "name": "The Addams Family",
                "manufacturer": "Williams",
                "month": 3,
                "year": 1992,
                "era": MachineModel.ERA_SS,
                "scoring": "DMD",
                "system": "Fliptronics 1?",
                "flipper_count": "4",
                "pinside_rating": 8.56,
                "ipdb_id": 20,
            },
            {
                "name": "Godzilla (Premium)",
                "manufacturer": "Stern",
                "month": 10,
                "year": 2021,
                "era": MachineModel.ERA_SS,
                "scoring": "video",
                "system": "Spike 2",
                "flipper_count": "3",
                "pinside_rating": 9.19,
                "ipdb_id": 6842,
            },
        ]

        # Create machine models
        models_created = 0
        models_existing = 0
        model_instances = {}

        for model_data in sample_models:
            model, created = MachineModel.objects.get_or_create(
                name=model_data["name"],
                defaults=model_data
            )

            model_instances[model_data["name"]] = model

            if created:
                models_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created model: {model.name} ({model.year} {model.manufacturer})'
                    )
                )
            else:
                models_existing += 1
                self.stdout.write(f'  Model already exists: {model.name}')

        # Sample machine instances with serial numbers and acquisition notes from legacy CSV
        sample_instances = [
            {
                "model_name": "Ballyhoo",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Carom",
                "serial_number": "?",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_UNKNOWN,
                "location": "",
            },
            {
                "model_name": "Trade Winds",
                "serial_number": "2450",
                "acquisition_notes": "Purchased June 2025 from a guy on FB Marketplace. It's a conversion of the 1941 Sky Blazer and the serial number is from there.",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_FIXING,
                "location": MachineInstance.LOCATION_WORKSHOP,
            },
            {
                "model_name": "Baseball",
                "serial_number": "24284",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_BROKEN,
                "location": MachineInstance.LOCATION_WORKSHOP,
            },
            {
                "model_name": "Derby Day",
                "serial_number": "AO4024DD",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Roto Pool",
                "serial_number": "87338RP",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Teacher's Pet",
                "serial_number": "34484",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Hokus Pokus",
                "serial_number": "2822",
                "acquisition_notes": "Bought 8/24/23 from Chuck in Pleasanton",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Star Trip",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Star Trek",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_FIXING,
                "location": MachineInstance.LOCATION_WORKSHOP,
            },
            {
                "model_name": "The Hulk",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Gorgar",
                "serial_number": "368844",
                "acquisition_notes": "Bought this from Matt Christiano circa May 2024 for $2k, including an NOS playfield. Not known to work.",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_FIXING,
                "location": MachineInstance.LOCATION_WORKSHOP,
            },
            {
                "model_name": "Blackout",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_FIXING,
                "location": MachineInstance.LOCATION_WORKSHOP,
            },
            {
                "model_name": "Hyperball",
                "serial_number": "560974",
                "acquisition_notes": "- Acquired for $800 from Jim Lewandowski of Riveriew IL on [[2024-12-19 Thursday]] - When purchased was in working shape with a couple of minor issues (sensors in top right)",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Eight Ball Deluxe Limited Edition",
                "serial_number": "E8B1147",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "The Getaway: High Speed II",
                "serial_number": "",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "The Addams Family",
                "serial_number": "24277",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
            {
                "model_name": "Godzilla (Premium)",
                "serial_number": "362497C",
                "acquisition_notes": "",
                "operational_status": MachineInstance.OPERATIONAL_STATUS_GOOD,
                "location": MachineInstance.LOCATION_FLOOR,
            },
        ]

        # Create machine instances
        instances_created = 0
        instances_existing = 0

        for instance_data in sample_instances:
            model_name = instance_data.pop("model_name")
            model = model_instances.get(model_name)

            if not model:
                self.stdout.write(
                    self.style.ERROR(f'✗ Model not found: {model_name}')
                )
                continue

            # Try to find existing instance by model and serial number
            instance, created = MachineInstance.objects.get_or_create(
                model=model,
                serial_number=instance_data["serial_number"],
                defaults=instance_data
            )

            if created:
                instances_created += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Created instance: {instance.name} (SN: {instance.serial_number or "N/A"})'
                    )
                )
            else:
                instances_existing += 1
                self.stdout.write(
                    f'  Instance already exists: {instance.name}'
                )

        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {models_created} models created, {models_existing} models already existed'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Summary: {instances_created} instances created, {instances_existing} instances already existed'
            )
        )
