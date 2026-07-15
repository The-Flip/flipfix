"""Tests for the write problem-report API (POST /api/v1/machines/<id>/problem-reports/)."""

from __future__ import annotations

import json
import secrets

from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineInstance
from flipfix.apps.core.models import ApiKey
from flipfix.apps.core.test_utils import create_machine
from flipfix.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class ProblemReportCreateApiAuthTests(TestCase):
    """Authentication and write-scope tests for the create endpoint."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.url = f"/api/v1/machines/{self.machine.asset_id}/problem-reports/"

    def _post(self, auth: str | None, body: dict | None = None):
        data = json.dumps(body or {})
        if auth is None:
            return self.client.post(self.url, data=data, content_type="application/json")
        return self.client.post(
            self.url,
            data=data,
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )

    def test_no_auth_header_returns_401(self):
        response = self._post(None, {"priority": "unplayable"})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_invalid_key_returns_403(self):
        response = self._post(f"Bearer {secrets.token_hex(32)}", {"priority": "minor"})
        self.assertEqual(response.status_code, 403)

    def test_read_only_key_returns_403(self):
        """A key without can_write cannot use the write endpoint."""
        key = ApiKey.objects.create(app_name="signage", can_write=False)
        response = self._post(f"Bearer {key.key}", {"priority": "minor"})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProblemReport.objects.exists())

    def test_unknown_machine_returns_404(self):
        key = ApiKey.objects.create(app_name="juice", can_write=True)
        response = self.client.post(
            "/api/v1/machines/M9999/problem-reports/",
            data=json.dumps({"priority": "minor"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {key.key}",
        )
        self.assertEqual(response.status_code, 404)


@tag("views")
class ProblemReportCreateApiBehaviorTests(TestCase):
    """Behavior tests for the create endpoint with a write-capable key."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.url = f"/api/v1/machines/{self.machine.asset_id}/problem-reports/"
        self.key = ApiKey.objects.create(app_name="juice", can_write=True)
        self.auth = f"Bearer {self.key.key}"

    def _post(self, body: dict):
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )

    def test_creates_unplayable_report(self):
        response = self._post(
            {
                "priority": "unplayable",
                "description": "Auto power-off: sustained overload",
                "reported_by_name": "Juice (automated overload detection)",
            }
        )
        self.assertEqual(response.status_code, 201)
        report = ProblemReport.objects.get()
        self.assertEqual(report.machine, self.machine)
        self.assertEqual(report.priority, ProblemReport.Priority.UNPLAYABLE)
        self.assertEqual(report.problem_type, ProblemReport.ProblemType.OTHER)
        self.assertEqual(report.reported_by_name, "Juice (automated overload detection)")
        self.assertEqual(report.status, ProblemReport.Status.OPEN)
        self.assertEqual(response.json()["problem_report"]["id"], report.pk)

    def test_mark_broken_sets_status_and_logs(self):
        response = self._post({"priority": "unplayable", "mark_broken": True})
        self.assertEqual(response.status_code, 201)

        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, MachineInstance.OperationalStatus.BROKEN)
        # The FieldTracker signal records the status change as a log entry.
        self.assertTrue(
            LogEntry.objects.filter(machine=self.machine, text__icontains="Broken").exists()
        )

    def test_unplayable_marks_broken_without_mark_broken(self):
        """An open Unplayable report breaks the machine even without mark_broken."""
        self._post({"priority": "unplayable"})
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, MachineInstance.OperationalStatus.BROKEN)

    def test_non_unplayable_leaves_status_untouched(self):
        """A non-Unplayable report without mark_broken does not change status."""
        self._post({"priority": "minor"})
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.operational_status, MachineInstance.OperationalStatus.GOOD)

    def test_idempotent_open_unplayable(self):
        """A second open unplayable report returns the existing one, no duplicate."""
        first = self._post({"priority": "unplayable", "description": "first"})
        self.assertEqual(first.status_code, 201)
        first_id = first.json()["problem_report"]["id"]

        second = self._post({"priority": "unplayable", "description": "second"})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["problem_report"]["id"], first_id)
        self.assertEqual(ProblemReport.objects.count(), 1)

    def test_non_unplayable_not_collapsed(self):
        """Idempotency only applies to unplayable; other priorities create each time."""
        self._post({"priority": "minor"})
        self._post({"priority": "minor"})
        self.assertEqual(ProblemReport.objects.count(), 2)

    def test_occurred_at_override(self):
        response = self._post({"priority": "minor", "occurred_at": "2026-01-02T03:04:05+00:00"})
        self.assertEqual(response.status_code, 201)
        report = ProblemReport.objects.get()
        self.assertEqual(report.occurred_at.isoformat(), "2026-01-02T03:04:05+00:00")

    def test_defaults_priority_to_minor(self):
        response = self._post({"description": "no priority given"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(ProblemReport.objects.get().priority, ProblemReport.Priority.MINOR)

    def test_invalid_priority_returns_400(self):
        response = self._post({"priority": "nonsense"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProblemReport.objects.exists())

    def test_invalid_problem_type_returns_400(self):
        response = self._post({"problem_type": "explosion"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_occurred_at_returns_400(self):
        response = self._post({"priority": "minor", "occurred_at": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProblemReport.objects.exists())

    def test_non_string_occurred_at_returns_400(self):
        """A non-string occurred_at is a 400, not a 500 (parse_datetime TypeError)."""
        response = self._post({"priority": "minor", "occurred_at": 123})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ProblemReport.objects.exists())

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            self.url,
            data="{not json",
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )
        self.assertEqual(response.status_code, 400)
