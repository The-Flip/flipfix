"""Tests for the pull_sample_machines management command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, tag

from flipfix.apps.catalog.models import MachineInstance, MachineModel

MODULE = "flipfix.apps.catalog.management.commands.pull_sample_machines"


def _api_payload() -> dict:
    """A fake /api/v1/machines/ response: two instances of one model, plus a sparse one."""
    tz_model = {
        "name": "Twilight Zone",
        "manufacturer": "Bally",
        "year": 1993,
        "month": 9,
        "era": "SS",
        "system": "WPC",
        "scoring": "points",
        "flipper_count": 3,
        "ipdb_id": 2684,
        "pinside_rating": 8.9,
    }
    ballyhoo_model = {
        "name": "Ballyhoo",
        "manufacturer": "Bally",
        "year": 1932,
        "month": 1,
        "era": "PM",
        "system": "",
        "scoring": "manual",
        "flipper_count": 0,
        "ipdb_id": 4817,
        "pinside_rating": None,
    }
    return {
        "machines": [
            {
                "asset_id": "M0001",
                "name": "Twilight Zone",
                "short_name": None,
                "slug": "tz-1",
                "serial_number": "111",
                "operational_status": "good",
                "location": "Floor",
                "model": tz_model,
            },
            {
                "asset_id": "M0002",
                "name": "Twilight Zone 2",
                "short_name": "TZ2",
                "slug": "tz-2",
                "serial_number": "222",
                "operational_status": "fixing",
                "location": "Workshop",
                "model": tz_model,
            },
            {
                "asset_id": "M0003",
                "name": "Ballyhoo",
                "short_name": None,
                "slug": "ballyhoo",
                "serial_number": "",
                "operational_status": "good",
                "location": None,
                "model": ballyhoo_model,
            },
        ]
    }


def _mock_response(payload: dict) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@tag("views")
class PullSampleMachinesTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.output = Path(self._tmp) / "machines.json"
        self.addCleanup(lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True))

    def _run(self, **kwargs):
        return call_command(
            "pull_sample_machines",
            "--api-key",
            "test-key",
            "--url",
            "http://example.test",
            "--output",
            str(self.output),
            **kwargs,
        )

    def test_groups_instances_into_fixture_shape(self):
        with patch(
            f"{MODULE}.requests.get", return_value=_mock_response(_api_payload())
        ) as mock_get:
            self._run()

        # Hit the documented endpoint with a Bearer header.
        url, kwargs = mock_get.call_args[0][0], mock_get.call_args[1]
        self.assertEqual(url, "http://example.test/api/v1/machines/")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")

        entries = json.loads(self.output.read_text())
        self.assertEqual([e["name"] for e in entries], ["Ballyhoo", "Twilight Zone"])  # by year

        ballyhoo, tz = entries
        # Blank/null model fields are omitted.
        self.assertNotIn("system", ballyhoo)
        self.assertNotIn("pinside_rating", ballyhoo)
        self.assertEqual(ballyhoo["era"], "PM")
        self.assertEqual(len(ballyhoo["instances"]), 1)
        bh_inst = ballyhoo["instances"][0]
        self.assertNotIn("serial_number", bh_inst)  # was ""
        self.assertNotIn("location", bh_inst)  # was null
        self.assertEqual(bh_inst["operational_status"], "good")

        # Twilight Zone keeps both instances; parity fields preserved.
        self.assertEqual(tz["pinside_rating"], 8.9)
        self.assertEqual(tz["ipdb_id"], 2684)
        self.assertEqual(len(tz["instances"]), 2)
        first, second = tz["instances"]
        # Instance name omitted when equal to the model name...
        self.assertNotIn("name", first)
        self.assertEqual(first["serial_number"], "111")
        self.assertEqual(first["location"], "Floor")
        # ...and kept when it differs (with short_name).
        self.assertEqual(second["name"], "Twilight Zone 2")
        self.assertEqual(second["short_name"], "TZ2")

    def test_dry_run_does_not_write(self):
        with patch(f"{MODULE}.requests.get", return_value=_mock_response(_api_payload())):
            self._run(dry_run=True)
        self.assertFalse(self.output.exists())

    def test_missing_api_key_raises(self):
        # Force decouple to return defaults (no key configured).
        with patch(f"{MODULE}.config", side_effect=lambda key, default=None: default):
            with self.assertRaises(CommandError):
                call_command("pull_sample_machines", "--output", str(self.output))

    def test_http_error_raises_command_error(self):
        with patch(f"{MODULE}.requests.get", side_effect=requests.ConnectionError("boom")):
            with self.assertRaises(CommandError):
                self._run()

    def test_regenerated_fixture_is_importable(self):
        """The written file round-trips through create_sample_machines."""
        from flipfix.apps.catalog.management.commands.create_sample_machines import (
            Command as CreateCommand,
        )

        with patch(f"{MODULE}.requests.get", return_value=_mock_response(_api_payload())):
            self._run()

        with patch.object(CreateCommand, "data_path", self.output):
            call_command("create_sample_machines")

        self.assertEqual(MachineModel.objects.count(), 2)
        self.assertEqual(MachineInstance.objects.count(), 3)
        # Grouping preserved: the two Twilight Zone instances share one model.
        tz = MachineModel.objects.get(name="Twilight Zone")
        self.assertEqual(tz.instances.count(), 2)
