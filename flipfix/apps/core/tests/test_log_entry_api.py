"""Tests for the write log-entry API (POST /api/v1/problem-reports/<pk>/log-entries/)."""

from __future__ import annotations

import json
import secrets
from uuid import uuid4

from django.test import TestCase, tag

from flipfix.apps.core.models import ApiKey
from flipfix.apps.core.test_utils import create_machine
from flipfix.apps.maintenance.models import LogEntry, ProblemReport


@tag("views")
class LogEntryCreateApiAuthTests(TestCase):
    """Authentication and write-scope tests for the create endpoint."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.report = ProblemReport.objects.create(
            machine=self.machine, priority=ProblemReport.Priority.UNPLAYABLE
        )
        self.url = f"/api/v1/problem-reports/{self.report.pk}/log-entries/"

    def _post(self, auth: str | None, body: dict | None = None):
        data = json.dumps(body or {"text": "x"})
        if auth is None:
            return self.client.post(self.url, data=data, content_type="application/json")
        return self.client.post(
            self.url, data=data, content_type="application/json", HTTP_AUTHORIZATION=auth
        )

    def test_no_auth_header_returns_401(self):
        response = self._post(None)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_invalid_key_returns_403(self):
        response = self._post(f"Bearer {secrets.token_hex(32)}")
        self.assertEqual(response.status_code, 403)

    def test_read_only_key_returns_403(self):
        """A key without can_write cannot use the write endpoint."""
        key = ApiKey.objects.create(app_name="signage", can_write=False)
        response = self._post(f"Bearer {key.key}")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(LogEntry.objects.exists())

    def test_unknown_report_returns_404(self):
        key = ApiKey.objects.create(app_name="juice", can_write=True)
        response = self.client.post(
            "/api/v1/problem-reports/999999/log-entries/",
            data=json.dumps({"text": "x"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {key.key}",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(LogEntry.objects.exists())


@tag("views")
class LogEntryCreateApiBehaviorTests(TestCase):
    """Behavior tests for the create endpoint with a write-capable key."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.report = ProblemReport.objects.create(
            machine=self.machine, priority=ProblemReport.Priority.UNPLAYABLE
        )
        self.url = f"/api/v1/problem-reports/{self.report.pk}/log-entries/"
        self.key = ApiKey.objects.create(app_name="juice", can_write=True)
        self.auth = f"Bearer {self.key.key}"

    def _post(self, body: dict):
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )

    def test_creates_log_entry(self):
        response = self._post(
            {
                "text": "Auto power-off recurrence: 182W peak vs 49W baseline over 3m12s",
                "reported_by_name": "Juice",
            }
        )
        self.assertEqual(response.status_code, 201)
        entry = LogEntry.objects.get()
        self.assertEqual(entry.problem_report, self.report)
        self.assertEqual(entry.machine, self.machine)
        self.assertEqual(
            entry.text, "Auto power-off recurrence: 182W peak vs 49W baseline over 3m12s"
        )
        self.assertEqual(entry.maintainer_names, "Juice")

        data = response.json()["log_entry"]
        self.assertEqual(data["id"], entry.pk)
        self.assertEqual(data["problem_report_id"], self.report.pk)
        self.assertEqual(data["machine_asset_id"], self.machine.asset_id)

    def test_reported_by_name_falls_back_to_app_name(self):
        """Without reported_by_name, attribution defaults to the API key's app_name."""
        response = self._post({"text": "shut down again"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(LogEntry.objects.get().maintainer_names, "juice")

    def test_occurred_at_override(self):
        response = self._post({"text": "x", "occurred_at": "2026-01-02T03:04:05+00:00"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            LogEntry.objects.get().occurred_at.isoformat(), "2026-01-02T03:04:05+00:00"
        )

    def test_missing_text_returns_400(self):
        response = self._post({"reported_by_name": "Juice"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_blank_text_returns_400(self):
        response = self._post({"text": "   "})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_invalid_occurred_at_returns_400(self):
        response = self._post({"text": "x", "occurred_at": "not-a-date"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_non_string_occurred_at_returns_400(self):
        """A non-string occurred_at is a 400, not a 500 (parse_datetime TypeError)."""
        response = self._post({"text": "x", "occurred_at": 123})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_overlong_reported_by_name_returns_400(self):
        response = self._post({"text": "x", "reported_by_name": "z" * 121})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            self.url,
            data="{not json",
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())


@tag("views")
class LogEntryCreateApiIdempotencyTests(TestCase):
    """An idempotency_key makes retried log-entry POSTs safe."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.report = ProblemReport.objects.create(
            machine=self.machine, priority=ProblemReport.Priority.UNPLAYABLE
        )
        self.url = f"/api/v1/problem-reports/{self.report.pk}/log-entries/"
        self.key = ApiKey.objects.create(app_name="juice", can_write=True)
        self.auth = f"Bearer {self.key.key}"

    def _post(self, body: dict):
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )

    def test_same_key_is_idempotent(self):
        """A retry with the same key returns the first entry with 200, no duplicate."""
        key = str(uuid4())

        first = self._post({"text": "shut down again", "idempotency_key": key})
        second = self._post({"text": "shut down again", "idempotency_key": key})

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(LogEntry.objects.count(), 1)
        self.assertEqual(first.json()["log_entry"]["id"], second.json()["log_entry"]["id"])

    def test_different_keys_create_separate_entries(self):
        """Distinct keys are distinct submissions and each creates an entry."""
        self._post({"text": "event one", "idempotency_key": str(uuid4())})
        self._post({"text": "event two", "idempotency_key": str(uuid4())})
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_without_key_every_call_creates(self):
        """Backwards-compatible: no key means a new 201 entry each time."""
        first = self._post({"text": "recurrence"})
        second = self._post({"text": "recurrence"})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_invalid_key_returns_400(self):
        """A non-UUID idempotency_key is rejected as a bad request."""
        response = self._post({"text": "x", "idempotency_key": "not-a-uuid"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(LogEntry.objects.exists())

    def test_key_reused_across_reports_returns_400(self):
        """A key already used on another report is rejected, not silently misdirected."""
        key = str(uuid4())
        self._post({"text": "first report", "idempotency_key": key})

        other_report = ProblemReport.objects.create(
            machine=self.machine, priority=ProblemReport.Priority.MAJOR
        )
        response = self.client.post(
            f"/api/v1/problem-reports/{other_report.pk}/log-entries/",
            data=json.dumps({"text": "second report", "idempotency_key": key}),
            content_type="application/json",
            HTTP_AUTHORIZATION=self.auth,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(LogEntry.objects.count(), 1)
