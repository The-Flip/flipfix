"""Regression tests: sample-data seeders tolerate a drifted machines.json.

machines.json is regenerated from the prod API, while logs_problems.json /
part_requests.json / the infinite-scroll target are hand-maintained, so they
drift. The seeders must skip stale machine references, not abort the whole seed.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, tag

from flipfix.apps.core.test_utils import TemporaryMediaMixin, create_machine
from flipfix.apps.maintenance.models import LogEntry, ProblemReport
from flipfix.apps.parts.models import PartRequest


@tag("commands")
class InfiniteScrollTargetFallbackTests(TestCase):
    def test_falls_back_to_any_machine_when_named_target_absent(self):
        # No machine named "Eight Ball 2"; the generator should use this one.
        machine = create_machine(name="Fallback Machine")
        call_command("create_sample_infinite_scrolling_data", stdout=StringIO())
        self.assertGreater(ProblemReport.objects.filter(machine=machine).count(), 0)

    def test_skips_gracefully_when_no_machines_exist(self):
        out = StringIO()
        call_command("create_sample_infinite_scrolling_data", stdout=out)
        self.assertIn("No machines", out.getvalue())
        self.assertEqual(ProblemReport.objects.count(), 0)


@tag("integration")
class FullSampleSeedTests(TemporaryMediaMixin, TestCase):
    def test_create_sample_data_completes_despite_drifted_fixtures(self):
        # Must not raise even though the fixtures reference machines that
        # machines.json no longer contains; the previously-aborting creators
        # (log entries, parts) now populate.
        call_command("create_sample_data", stdout=StringIO())
        self.assertGreater(LogEntry.objects.count(), 0)
        self.assertGreater(PartRequest.objects.count(), 0)
