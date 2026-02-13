"""Tests for register_reference_cleanup() helper."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag

from the_flip.apps.core.markdown_links import sync_references
from the_flip.apps.core.models import RecordReference
from the_flip.apps.core.test_utils import create_machine


@tag("models")
class RegisterReferenceCleanupTests(TestCase):
    """Verify that deleting a source record removes its RecordReference rows.

    The cleanup is wired via register_reference_cleanup() in each app's
    AppConfig.ready(), so these tests exercise the real signal wiring.
    """

    @classmethod
    def setUpTestData(cls):
        cls.machine = create_machine()

    def test_deleting_log_entry_removes_references(self):
        """RecordReference rows for a LogEntry are deleted when the entry is deleted."""
        from the_flip.apps.maintenance.models import LogEntry

        other = create_machine(slug="other", name="Other")
        entry = LogEntry.objects.create(machine=self.machine, text="test")

        # Create a reference from entry → other machine
        sync_references(entry, f"See [[machine:id:{other.pk}]].")
        source_ct = ContentType.objects.get_for_model(LogEntry)
        self.assertTrue(
            RecordReference.objects.filter(source_type=source_ct, source_id=entry.pk).exists()
        )

        entry.delete()

        self.assertFalse(
            RecordReference.objects.filter(source_type=source_ct, source_id=entry.pk).exists()
        )

    def test_deleting_problem_report_removes_references(self):
        """RecordReference rows for a ProblemReport are deleted when the report is deleted."""
        from the_flip.apps.maintenance.models import ProblemReport

        other = create_machine(slug="other2", name="Other2")
        report = ProblemReport.objects.create(machine=self.machine, description="broken")

        sync_references(report, f"See [[machine:id:{other.pk}]].")
        source_ct = ContentType.objects.get_for_model(ProblemReport)
        self.assertTrue(
            RecordReference.objects.filter(source_type=source_ct, source_id=report.pk).exists()
        )

        report.delete()

        self.assertFalse(
            RecordReference.objects.filter(source_type=source_ct, source_id=report.pk).exists()
        )

    def test_deleting_part_request_removes_references(self):
        """RecordReference rows for a PartRequest are deleted when the request is deleted."""
        from the_flip.apps.core.test_utils import create_maintainer_user
        from the_flip.apps.parts.models import PartRequest

        user = create_maintainer_user()
        maintainer = user.maintainer
        other = create_machine(slug="other3", name="Other3")
        part_request = PartRequest.objects.create(
            machine=self.machine,
            requested_by=maintainer,
            text="need parts",
        )

        sync_references(part_request, f"See [[machine:id:{other.pk}]].")
        source_ct = ContentType.objects.get_for_model(PartRequest)
        self.assertTrue(
            RecordReference.objects.filter(
                source_type=source_ct, source_id=part_request.pk
            ).exists()
        )

        part_request.delete()

        self.assertFalse(
            RecordReference.objects.filter(
                source_type=source_ct, source_id=part_request.pk
            ).exists()
        )
