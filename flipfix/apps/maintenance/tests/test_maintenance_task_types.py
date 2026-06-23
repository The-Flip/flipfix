"""Tests for MaintenanceTaskType, the log-work task field, and the mark-done view."""

from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from flipfix.apps.core.test_utils import (
    DATETIME_INPUT_FORMAT,
    TestDataMixin,
    create_log_entry,
    create_user,
)
from flipfix.apps.maintenance.forms import LogEntryQuickForm
from flipfix.apps.maintenance.models import LogEntry, MaintenanceTaskType

SEED_SLUGS = {"clean-playfield", "replace-balls", "replace-rubbers"}


@tag("models")
class MaintenanceTaskTypeModelTests(TestCase):
    def test_slug_autofilled_from_name(self):
        task = MaintenanceTaskType.objects.create(name="Wax The Ramps")
        self.assertEqual(task.slug, "wax-the-ramps")

    def test_explicit_slug_preserved(self):
        task = MaintenanceTaskType.objects.create(name="Foo", slug="custom")
        self.assertEqual(task.slug, "custom")

    def test_str(self):
        self.assertEqual(str(MaintenanceTaskType(name="Clean")), "Clean")

    def test_default_active(self):
        self.assertTrue(MaintenanceTaskType.objects.create(name="Bumpers").is_active)

    def test_ordering_by_sort_order_then_name(self):
        MaintenanceTaskType.objects.all().delete()
        beta = MaintenanceTaskType.objects.create(name="Beta", sort_order=2)
        alpha = MaintenanceTaskType.objects.create(name="Alpha", sort_order=1)
        self.assertEqual(list(MaintenanceTaskType.objects.all()), [alpha, beta])

    def test_seed_data_present(self):
        slugs = set(MaintenanceTaskType.objects.values_list("slug", flat=True))
        self.assertTrue(SEED_SLUGS <= slugs)

    def test_log_entry_m2m(self):
        entry = create_log_entry()
        task = MaintenanceTaskType.objects.get(slug="clean-playfield")
        entry.maintenance_tasks.add(task)
        self.assertEqual(list(entry.maintenance_tasks.all()), [task])
        self.assertIn(entry, task.log_entries.all())


@tag("forms")
class LogWorkTaskFieldTests(TestCase):
    def test_form_excludes_inactive_tasks(self):
        MaintenanceTaskType.objects.create(name="Hidden", slug="hidden", is_active=False)
        queryset = LogEntryQuickForm().fields["maintenance_tasks"].queryset
        slugs = set(queryset.values_list("slug", flat=True))
        self.assertIn("clean-playfield", slugs)
        self.assertNotIn("hidden", slugs)


@tag("views")
class MachineLogCreateTaskTests(TestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("log-create-machine", kwargs={"slug": self.machine.slug})
        self.task = MaintenanceTaskType.objects.get(slug="clean-playfield")

    def test_create_tags_selected_task(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.post(
            self.url,
            {
                "occurred_at": timezone.now().strftime(DATETIME_INPUT_FORMAT),
                "maintainer_freetext": "Test User",
                "text": "Cleaned it up",
                "maintenance_tasks": [self.task.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        entry = LogEntry.objects.latest("id")
        self.assertEqual(list(entry.maintenance_tasks.all()), [self.task])


@tag("views")
class MarkTaskDoneViewTests(TestDataMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.task = MaintenanceTaskType.objects.get(slug="clean-playfield")
        self.url = reverse(
            "machine-mark-task-done",
            kwargs={"slug": self.machine.slug, "task_slug": self.task.slug},
        )

    def test_post_creates_tagged_attributed_entry(self):
        self.client.force_login(self.maintainer_user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        entry = LogEntry.objects.latest("id")
        self.assertEqual(entry.machine, self.machine)
        self.assertEqual(entry.text, f"Routine: {self.task.name}")
        self.assertEqual(list(entry.maintenance_tasks.all()), [self.task])
        # clean() invariant: must carry a maintainer or a maintainer name
        self.assertTrue(entry.maintainers.exists() or entry.maintainer_names)

    def test_get_not_allowed(self):
        self.client.force_login(self.maintainer_user)
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_inactive_task_returns_404(self):
        self.task.is_active = False
        self.task.save()
        self.client.force_login(self.maintainer_user)
        before = LogEntry.objects.count()
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertEqual(LogEntry.objects.count(), before)

    def test_non_maintainer_blocked(self):
        self.client.force_login(create_user())
        before = LogEntry.objects.count()
        response = self.client.post(self.url)
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(LogEntry.objects.count(), before)
