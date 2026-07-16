"""Tests for the `daily_maintenance_report` management command."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import TestCase, tag

from flipfix.apps.catalog.models import Location, MachineInstance
from flipfix.apps.core.test_utils import (
    create_location,
    create_machine,
    create_machine_model,
)

S = MachineInstance.OperationalStatus
Z = Location.Zone


@tag("commands")
class DailyReportCommandTests(TestCase):
    def setUp(self):
        self.front = create_location("Coin-Op", Z.FRONT)

    def test_prints_digest(self):
        create_machine(location=self.front, model=create_machine_model())
        out = StringIO()
        call_command("daily_maintenance_report", stdout=out)
        self.assertIn("**Front of House:**", out.getvalue())

    def test_verbose_lists_machines(self):
        create_machine(location=self.front, name="Gorgar", model=create_machine_model(year=1979))
        out = StringIO()
        call_command("daily_maintenance_report", "--verbose", stdout=out)
        self.assertIn("Gorgar (1979)", out.getvalue())

    def test_runs_with_no_machines(self):
        out = StringIO()
        call_command("daily_maintenance_report", stdout=out)
        self.assertIn("Front of House", out.getvalue())
