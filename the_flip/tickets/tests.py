from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import ProblemReportCreateForm
from .models import MachineModel, MachineInstance, Maintainer, ProblemReport


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)
class ReportCreateViewTests(TestCase):
    def setUp(self):
        cache.clear()
        # Create a machine model and instance
        self.model = MachineModel.objects.create(
            name='Test Game',
            manufacturer='Bally',
            year=1995,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
        )
        self.url = reverse('report_create')

    def _submission_payload(self, **overrides):
        payload = {
            'machine': self.machine.pk,
            'problem_type': ProblemReport.PROBLEM_STUCK_BALL,
            'problem_text': 'Ball stuck in left ramp.',
            'reported_by_name': 'Visitor',
            'reported_by_contact': 'visitor@example.com',
        }
        payload.update(overrides)
        return payload

    def test_anonymous_submission_records_ip(self):
        response = self.client.post(
            self.url,
            self._submission_payload(),
            HTTP_USER_AGENT='UnitTest/1.0',
            HTTP_X_FORWARDED_FOR='203.0.113.5',
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.get()
        self.assertIsNone(report.reported_by_user)
        self.assertEqual(report.reported_by_name, 'Visitor')
        self.assertEqual(report.ip_address, '203.0.113.5')
        self.assertEqual(report.device_info, 'UnitTest/1.0')

    def test_authenticated_submission_records_user_and_contact(self):
        user = get_user_model().objects.create_user(
            username='maintainer',
            email='tech@example.com',
            password='pass1234',
            first_name='Tech',
            last_name='One',
        )
        Maintainer.objects.create(user=user, phone='555-1234')
        self.client.login(username='maintainer', password='pass1234')

        response = self.client.post(
            self.url,
            self._submission_payload(problem_text='Coil burnt out.'),
            REMOTE_ADDR='198.51.100.42',
        )
        self.assertEqual(response.status_code, 302)
        report = ProblemReport.objects.get()
        self.assertEqual(report.reported_by_user, user)
        self.assertEqual(report.reported_by_name, 'Tech One')
        self.assertEqual(report.reported_by_contact, 'tech@example.com')
        self.assertEqual(report.ip_address, '198.51.100.42')

    @override_settings(REPORT_SUBMISSION_RATE_LIMIT_MAX=2, REPORT_SUBMISSION_RATE_LIMIT_WINDOW_SECONDS=3600)
    def test_rate_limit_blocks_submissions_from_same_ip(self):
        payload = self._submission_payload(problem_text='Repeated issue.')
        headers = {'HTTP_X_FORWARDED_FOR': '203.0.113.8'}

        for _ in range(2):
            response = self.client.post(self.url, payload, **headers)
            self.assertEqual(response.status_code, 302)

        response = self.client.post(self.url, payload, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many problem reports from this device', status_code=200)
        self.assertEqual(ProblemReport.objects.count(), 2)


class ProblemReportFormMachineFilteringTests(TestCase):
    """Tests for machine filtering in ProblemReportCreateForm based on user authentication."""

    def setUp(self):
        # Create a machine model
        self.model = MachineModel.objects.create(
            name='Test Pinball',
            manufacturer='Williams',
            year=1992,
            era=MachineModel.ERA_SS,
        )

        # Create machines in different locations and statuses
        self.floor_good = MachineInstance.objects.create(
            model=self.model,
            name_override='Floor Good',
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
        )
        self.floor_broken = MachineInstance.objects.create(
            model=self.model,
            name_override='Floor Broken',
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN,
        )
        self.workshop_good = MachineInstance.objects.create(
            model=self.model,
            name_override='Workshop Good',
            location=MachineInstance.LOCATION_WORKSHOP,
            operational_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
        )
        self.workshop_broken = MachineInstance.objects.create(
            model=self.model,
            name_override='Workshop Broken',
            location=MachineInstance.LOCATION_WORKSHOP,
            operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN,
        )
        self.storage_good = MachineInstance.objects.create(
            model=self.model,
            name_override='Storage Good',
            location=MachineInstance.LOCATION_STORAGE,
            operational_status=MachineInstance.OPERATIONAL_STATUS_GOOD,
        )

        # Create a user for authenticated tests
        self.user = get_user_model().objects.create_user(
            username='testuser',
            password='testpass123'
        )

    def test_unauthenticated_user_sees_only_floor_machines(self):
        """Unauthenticated users should only see machines on the floor."""
        form = ProblemReportCreateForm(user=None)
        queryset = form.fields['machine'].queryset
        machine_ids = set(queryset.values_list('id', flat=True))

        # Should include both floor machines
        self.assertIn(self.floor_good.id, machine_ids)
        self.assertIn(self.floor_broken.id, machine_ids)

        # Should NOT include workshop or storage machines
        self.assertNotIn(self.workshop_good.id, machine_ids)
        self.assertNotIn(self.workshop_broken.id, machine_ids)
        self.assertNotIn(self.storage_good.id, machine_ids)

    def test_unauthenticated_user_sees_broken_machines_on_floor(self):
        """Unauthenticated users should see broken machines if they're on the floor."""
        form = ProblemReportCreateForm(user=None)
        queryset = form.fields['machine'].queryset
        machine_ids = set(queryset.values_list('id', flat=True))

        # Broken machine on floor should be visible
        self.assertIn(self.floor_broken.id, machine_ids)

    def test_authenticated_user_sees_all_machines(self):
        """Authenticated users should see machines in all locations."""
        form = ProblemReportCreateForm(user=self.user)
        queryset = form.fields['machine'].queryset
        machine_ids = set(queryset.values_list('id', flat=True))

        # Should include all machines regardless of location
        self.assertIn(self.floor_good.id, machine_ids)
        self.assertIn(self.floor_broken.id, machine_ids)
        self.assertIn(self.workshop_good.id, machine_ids)
        self.assertIn(self.workshop_broken.id, machine_ids)
        self.assertIn(self.storage_good.id, machine_ids)

    def test_authenticated_user_sees_broken_machines(self):
        """Authenticated users should see broken machines."""
        form = ProblemReportCreateForm(user=self.user)
        queryset = form.fields['machine'].queryset
        machine_ids = set(queryset.values_list('id', flat=True))

        # Should include broken machines
        self.assertIn(self.floor_broken.id, machine_ids)
        self.assertIn(self.workshop_broken.id, machine_ids)

    def test_qr_code_scenario_bypasses_filtering(self):
        """When machine is pre-selected via QR code, filtering doesn't apply."""
        # Workshop machine should be usable via QR code even for unauthenticated users
        form = ProblemReportCreateForm(machine=self.workshop_good, user=None)

        # Machine field should be hidden
        self.assertIsInstance(form.fields['machine'].widget, form.fields['machine'].hidden_widget().__class__)

        # Machine should be pre-selected
        self.assertEqual(form.fields['machine'].initial, self.workshop_good)


class MachineInstanceSlugTests(TestCase):
    """Tests for slug auto-generation and uniqueness."""

    def setUp(self):
        self.model = MachineModel.objects.create(
            name='The Addams Family',
            manufacturer='Williams',
            year=1992,
            era=MachineModel.ERA_SS,
        )

    def test_slug_auto_generation_from_model_name(self):
        """Slug should be auto-generated from model name when no name_override."""
        machine = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
        )
        self.assertEqual(machine.slug, 'the-addams-family')

    def test_slug_auto_generation_from_name_override(self):
        """Slug should be auto-generated from name_override when provided."""
        machine = MachineInstance.objects.create(
            model=self.model,
            name_override='TAF Special Edition',
            location=MachineInstance.LOCATION_FLOOR,
        )
        self.assertEqual(machine.slug, 'taf-special-edition')

    def test_slug_uniqueness_automatic_suffix(self):
        """Second instance with same name should get -2 suffix."""
        machine1 = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
        )
        machine2 = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_WORKSHOP,
        )

        self.assertEqual(machine1.slug, 'the-addams-family')
        self.assertEqual(machine2.slug, 'the-addams-family-2')

    def test_slug_uniqueness_third_instance(self):
        """Third instance should get -3 suffix."""
        machine1 = MachineInstance.objects.create(model=self.model)
        machine2 = MachineInstance.objects.create(model=self.model)
        machine3 = MachineInstance.objects.create(model=self.model)

        self.assertEqual(machine1.slug, 'the-addams-family')
        self.assertEqual(machine2.slug, 'the-addams-family-2')
        self.assertEqual(machine3.slug, 'the-addams-family-3')

    def test_slug_manual_override(self):
        """Manually setting slug should be preserved."""
        machine = MachineInstance.objects.create(
            model=self.model,
            slug='custom-slug',
            location=MachineInstance.LOCATION_FLOOR,
        )
        self.assertEqual(machine.slug, 'custom-slug')

    def test_slug_update_on_save(self):
        """Changing name_override should not change existing slug."""
        machine = MachineInstance.objects.create(
            model=self.model,
            name_override='Original Name',
        )
        original_slug = machine.slug

        machine.name_override = 'New Name'
        machine.save()

        # Slug should remain unchanged
        self.assertEqual(machine.slug, original_slug)


class MachineInstanceQuerysetTests(TestCase):
    """Tests for MachineInstance custom querysets."""

    def setUp(self):
        self.model = MachineModel.objects.create(
            name='Test Machine',
            manufacturer='Test Corp',
            year=2000,
            era=MachineModel.ERA_SS,
        )

        # Create machines in different locations
        self.floor_machines = [
            MachineInstance.objects.create(
                model=self.model,
                name_override=f'Floor Machine {i}',
                location=MachineInstance.LOCATION_FLOOR,
            ) for i in range(3)
        ]

        self.workshop_machines = [
            MachineInstance.objects.create(
                model=self.model,
                name_override=f'Workshop Machine {i}',
                location=MachineInstance.LOCATION_WORKSHOP,
            ) for i in range(2)
        ]

        self.storage_machines = [
            MachineInstance.objects.create(
                model=self.model,
                name_override=f'Storage Machine {i}',
                location=MachineInstance.LOCATION_STORAGE,
            ) for i in range(1)
        ]

    def test_on_floor_queryset(self):
        """on_floor() should return only machines on the floor."""
        floor_machines = MachineInstance.objects.on_floor()
        self.assertEqual(floor_machines.count(), 3)
        for machine in floor_machines:
            self.assertEqual(machine.location, MachineInstance.LOCATION_FLOOR)

    def test_in_workshop_queryset(self):
        """in_workshop() should return only machines in workshop."""
        workshop_machines = MachineInstance.objects.in_workshop()
        self.assertEqual(workshop_machines.count(), 2)
        for machine in workshop_machines:
            self.assertEqual(machine.location, MachineInstance.LOCATION_WORKSHOP)

    def test_in_storage_queryset(self):
        """in_storage() should return only machines in storage."""
        storage_machines = MachineInstance.objects.in_storage()
        self.assertEqual(storage_machines.count(), 1)
        for machine in storage_machines:
            self.assertEqual(machine.location, MachineInstance.LOCATION_STORAGE)

    def test_by_name_with_name_override(self):
        """by_name() should find machines by their name_override."""
        results = MachineInstance.objects.by_name('Floor Machine 0')
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().name_override, 'Floor Machine 0')

    def test_by_name_with_model_name(self):
        """by_name() should find machines by their model name."""
        # Create a machine without name_override
        machine = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
        )
        results = MachineInstance.objects.by_name('Test Machine')
        self.assertIn(machine, results)

    def test_by_name_no_results(self):
        """by_name() should return empty queryset for non-existent name."""
        results = MachineInstance.objects.by_name('Nonexistent Machine')
        self.assertEqual(results.count(), 0)


class MachineInstanceNamePropertyTests(TestCase):
    """Tests for MachineInstance name property behavior."""

    def setUp(self):
        self.model = MachineModel.objects.create(
            name='Star Trek',
            manufacturer='Bally',
            year=1979,
            era=MachineModel.ERA_SS,
        )

    def test_name_property_uses_model_name_by_default(self):
        """name property should return model name when no override."""
        machine = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
        )
        self.assertEqual(machine.name, 'Star Trek')

    def test_name_property_uses_override_when_set(self):
        """name property should return name_override when set."""
        machine = MachineInstance.objects.create(
            model=self.model,
            name_override='Star Trek Limited Edition',
            location=MachineInstance.LOCATION_FLOOR,
        )
        self.assertEqual(machine.name, 'Star Trek Limited Edition')

    def test_name_property_falls_back_after_override_cleared(self):
        """name property should fall back to model name if override is cleared."""
        machine = MachineInstance.objects.create(
            model=self.model,
            name_override='Custom Name',
        )
        self.assertEqual(machine.name, 'Custom Name')

        machine.name_override = ''
        machine.save()
        self.assertEqual(machine.name, 'Star Trek')

    def test_str_uses_name_property(self):
        """__str__() should use the name property."""
        machine = MachineInstance.objects.create(
            model=self.model,
            name_override='Custom Name',
        )
        self.assertEqual(str(machine), 'Custom Name')

    def test_name_propagates_from_model_changes(self):
        """Changing model name should propagate to instances without override."""
        machine = MachineInstance.objects.create(model=self.model)
        self.assertEqual(machine.name, 'Star Trek')

        self.model.name = 'Star Trek: The Next Generation'
        self.model.save()
        machine.refresh_from_db()

        self.assertEqual(machine.name, 'Star Trek: The Next Generation')


class MachineStatusReportIntegrationTests(TestCase):
    """Tests for machine status changes affecting problem reports."""

    def setUp(self):
        self.model = MachineModel.objects.create(
            name='Test Pinball',
            manufacturer='Test',
            year=1990,
            era=MachineModel.ERA_SS,
        )
        self.machine = MachineInstance.objects.create(
            model=self.model,
            location=MachineInstance.LOCATION_FLOOR,
            operational_status=MachineInstance.OPERATIONAL_STATUS_BROKEN,
        )
        self.user = get_user_model().objects.create_user(
            username='maintainer',
            password='testpass'
        )
        self.maintainer = Maintainer.objects.create(user=self.user)

        self.report = ProblemReport.objects.create(
            machine=self.machine,
            problem_type=ProblemReport.PROBLEM_OTHER,
            problem_text='Test problem',
            status=ProblemReport.STATUS_OPEN,
        )

    def test_setting_machine_good_closes_report(self):
        """Setting machine status to 'good' should close the report."""
        update = self.report.set_machine_status(
            MachineInstance.OPERATIONAL_STATUS_GOOD,
            self.maintainer,
            "Fixed!"
        )
        self.report.refresh_from_db()
        self.machine.refresh_from_db()

        self.assertEqual(self.report.status, ProblemReport.STATUS_CLOSED)
        self.assertEqual(self.machine.operational_status, MachineInstance.OPERATIONAL_STATUS_GOOD)
        self.assertEqual(update.status, ProblemReport.STATUS_CLOSED)
        self.assertEqual(update.machine_status, MachineInstance.OPERATIONAL_STATUS_GOOD)

    def test_setting_machine_broken_opens_report(self):
        """Setting machine status to 'broken' should open the report."""
        # First close the report
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        # Then set machine to broken
        update = self.report.set_machine_status(
            MachineInstance.OPERATIONAL_STATUS_BROKEN,
            self.maintainer,
            "Problem returned"
        )
        self.report.refresh_from_db()

        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)
        self.assertEqual(update.status, ProblemReport.STATUS_OPEN)

    def test_setting_machine_fixing_opens_report(self):
        """Setting machine status to 'fixing' should keep/open the report."""
        self.report.status = ProblemReport.STATUS_CLOSED
        self.report.save()

        update = self.report.set_machine_status(
            MachineInstance.OPERATIONAL_STATUS_FIXING,
            self.maintainer,
            "Working on it"
        )
        self.report.refresh_from_db()

        self.assertEqual(self.report.status, ProblemReport.STATUS_OPEN)

    def test_setting_machine_unknown_does_not_change_report(self):
        """Setting machine status to 'unknown' should not change report status."""
        original_status = self.report.status

        update = self.report.set_machine_status(
            MachineInstance.OPERATIONAL_STATUS_UNKNOWN,
            self.maintainer,
            "Status unclear"
        )
        self.report.refresh_from_db()

        self.assertEqual(self.report.status, original_status)
