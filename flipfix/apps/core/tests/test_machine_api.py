"""Tests for the read-only machine API (/api/v1/machines/)."""

from __future__ import annotations

import secrets

from django.db import IntegrityError
from django.test import TestCase, tag

from flipfix.apps.catalog.models import Location
from flipfix.apps.core.models import ApiKey
from flipfix.apps.core.test_utils import create_machine, create_machine_model


@tag("views")
class MachineListApiAuthTests(TestCase):
    """Authentication tests for the machine list API."""

    url = "/api/v1/machines/"

    def test_no_auth_header_returns_401(self):
        """Request without Authorization header is rejected."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_invalid_key_returns_403(self):
        """Request with an unrecognized API key is rejected."""
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {secrets.token_hex(32)}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_malformed_auth_header_returns_401(self):
        """Authorization header without 'Bearer ' prefix is rejected."""
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION="Token abc123",
        )
        self.assertEqual(response.status_code, 401)

    def test_valid_key_returns_200(self):
        """Request with a valid API key succeeds."""
        api_key = ApiKey.objects.create(app_name="test-app")
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {api_key.key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("machines", response.json())

    def test_post_not_allowed(self):
        """POST requests return 405 Method Not Allowed."""
        api_key = ApiKey.objects.create(app_name="test-app")
        response = self.client.post(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {api_key.key}",
        )
        self.assertEqual(response.status_code, 405)


@tag("views")
class MachineListApiResponseTests(TestCase):
    """Response shape and content tests for the machine list API."""

    url = "/api/v1/machines/"

    def setUp(self):
        self.api_key = ApiKey.objects.create(app_name="test-app")
        self.auth_header = f"Bearer {self.api_key.key}"

    def _get(self):
        return self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)

    def test_empty_list(self):
        """Returns empty list when no machines exist."""
        response = self._get()
        self.assertEqual(response.json(), {"machines": []})

    def test_machine_fields(self):
        """Response includes all expected fields."""
        location = Location.objects.create(name="Main Floor")
        model = create_machine_model(
            name="Medieval Madness",
            manufacturer="Williams",
            year=1997,
        )
        machine = create_machine(
            model=model,
            name="Medieval Madness",
        )
        machine.location = location
        machine.serial_number = "SN-12345"
        machine.save()

        response = self._get()
        data = response.json()

        self.assertEqual(len(data["machines"]), 1)
        m = data["machines"][0]

        self.assertEqual(m["asset_id"], machine.asset_id)
        self.assertEqual(m["name"], "Medieval Madness")
        self.assertEqual(m["slug"], machine.slug)
        self.assertEqual(m["serial_number"], "SN-12345")
        self.assertEqual(m["operational_status"], "good")
        self.assertEqual(m["location"], "Main Floor")
        self.assertEqual(m["model"]["name"], "Medieval Madness")
        self.assertEqual(m["model"]["manufacturer"], "Williams")
        self.assertEqual(m["model"]["year"], 1997)

    def test_null_location(self):
        """Machine with no location returns null for location field."""
        create_machine(name="No Location Machine")

        response = self._get()
        m = response.json()["machines"][0]
        self.assertIsNone(m["location"])

    def test_no_owner_in_response(self):
        """Owner information is not exposed in the API response."""
        create_machine(name="Test Machine")

        response = self._get()
        m = response.json()["machines"][0]
        self.assertNotIn("owner", m)

    def test_multiple_machines_ordered_by_model_sort_name(self):
        """Machines are ordered alphabetically by model sort name."""
        # sort_name strips leading articles, so "The Addams Family" -> "Addams Family"
        model_a = create_machine_model(name="The Addams Family")
        model_b = create_machine_model(name="Attack From Mars")
        model_c = create_machine_model(name="Twilight Zone")
        create_machine(model=model_c, name="Twilight Zone")
        create_machine(model=model_b, name="Attack From Mars")
        create_machine(model=model_a, name="The Addams Family")

        response = self._get()
        names = [m["name"] for m in response.json()["machines"]]
        self.assertEqual(names, ["The Addams Family", "Attack From Mars", "Twilight Zone"])


@tag("views")
class MachineDetailApiAuthTests(TestCase):
    """Authentication tests for the machine detail API."""

    def setUp(self):
        self.machine = create_machine(name="Test Machine")
        self.url = f"/api/v1/machines/{self.machine.asset_id}/"

    def test_no_auth_header_returns_401(self):
        """Request without Authorization header is rejected."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_invalid_key_returns_403(self):
        """Request with an unrecognized API key is rejected."""
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {secrets.token_hex(32)}",
        )
        self.assertEqual(response.status_code, 403)

    def test_valid_key_returns_200(self):
        """Request with a valid API key succeeds."""
        api_key = ApiKey.objects.create(app_name="test-app")
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f"Bearer {api_key.key}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("machine", response.json())


@tag("views")
class MachineDetailApiResponseTests(TestCase):
    """Response shape and content tests for the machine detail API."""

    def setUp(self):
        self.api_key = ApiKey.objects.create(app_name="test-app")
        self.auth_header = f"Bearer {self.api_key.key}"

    def _get(self, asset_id: str):
        return self.client.get(
            f"/api/v1/machines/{asset_id}/",
            HTTP_AUTHORIZATION=self.auth_header,
        )

    def test_returns_machine_by_asset_id(self):
        """Returns the correct machine for a given asset ID."""
        location = Location.objects.create(name="Main Floor")
        model = create_machine_model(
            name="Medieval Madness",
            manufacturer="Williams",
            year=1997,
        )
        machine = create_machine(model=model, name="Medieval Madness")
        machine.location = location
        machine.save()

        response = self._get(machine.asset_id)
        data = response.json()

        m = data["machine"]
        self.assertEqual(m["asset_id"], machine.asset_id)
        self.assertEqual(m["name"], "Medieval Madness")
        self.assertEqual(m["location"], "Main Floor")
        self.assertEqual(m["model"]["manufacturer"], "Williams")

    def test_case_insensitive_lookup(self):
        """Asset ID lookup is case-insensitive."""
        machine = create_machine(name="Test Machine")

        response = self._get(machine.asset_id.lower())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["machine"]["asset_id"], machine.asset_id)

    def test_not_found_returns_404(self):
        """Non-existent asset ID returns 404."""
        response = self._get("M9999")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json()["success"])

    def test_no_owner_in_response(self):
        """Owner information is not exposed in the detail response."""
        machine = create_machine(name="Test Machine")

        response = self._get(machine.asset_id)
        self.assertNotIn("owner", response.json()["machine"])


@tag("models")
class ApiKeyModelTests(TestCase):
    """Tests for the ApiKey model."""

    def test_auto_generates_key_on_create(self):
        """Key is auto-generated when not provided."""
        api_key = ApiKey.objects.create(app_name="test-app")
        self.assertEqual(len(api_key.key), 64)  # 32 bytes = 64 hex chars

    def test_preserves_explicit_key(self):
        """Explicit key is preserved, not overwritten."""
        explicit_key = secrets.token_hex(32)
        api_key = ApiKey.objects.create(app_name="test-app", key=explicit_key)
        self.assertEqual(api_key.key, explicit_key)

    def test_str_shows_app_name_and_key_prefix(self):
        """String representation shows app name and key prefix."""
        api_key = ApiKey.objects.create(app_name="signage-app")
        self.assertIn("signage-app", str(api_key))
        self.assertIn(api_key.key[:8], str(api_key))

    def test_key_uniqueness(self):
        """Keys must be unique."""
        key = secrets.token_hex(32)
        ApiKey.objects.create(app_name="app-1", key=key)
        with self.assertRaises(IntegrityError):
            ApiKey.objects.create(app_name="app-2", key=key)
