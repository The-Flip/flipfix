"""Refresh the committed sample-data fixture from the production machine API.

Maintainer tool: fetches ``/api/v1/machines/`` and rewrites
``docs/sample_data/records/machines.json`` (the fixture that
``create_sample_machines`` loads). It never touches the database and is
deliberately *not* part of ``create_sample_data`` (which stays offline).

Fields the API does not expose (e.g. ``acquisition_notes``, ``owner``) are not
regenerated, by design — the API is the privacy boundary for the public repo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from decouple import config
from django.core.management.base import BaseCommand, CommandError

DEFAULT_URL = "https://flipfix.theflip.museum"
DEFAULT_OUTPUT = Path("docs/sample_data/records/machines.json")
REQUEST_TIMEOUT = 30

# Model-level keys, in the order the fixture presents them.
MODEL_FIELD_ORDER = (
    "name",
    "manufacturer",
    "month",
    "year",
    "era",
    "system",
    "scoring",
    "flipper_count",
    "pinside_rating",
    "ipdb_id",
)


class Command(BaseCommand):
    help = (
        "Fetch machines from the production API and rewrite the committed sample-data "
        "fixture (docs/sample_data/records/machines.json). Maintainers only; requires an "
        "API key (--api-key or $SAMPLE_DATA_API_KEY). Fields the API does not expose "
        "(e.g. acquisition_notes) are not regenerated."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--url", help="API base URL (default: $SAMPLE_DATA_API_URL or production)."
        )
        parser.add_argument("--api-key", help="Bearer API key (default: $SAMPLE_DATA_API_KEY).")
        parser.add_argument(
            "--output",
            type=Path,
            default=DEFAULT_OUTPUT,
            help=f"Fixture path to write (default: {DEFAULT_OUTPUT}).",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Summarize without writing the file."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        base_url = (
            options.get("url") or config("SAMPLE_DATA_API_URL", default=DEFAULT_URL)
        ).rstrip("/")
        api_key = options.get("api_key") or config("SAMPLE_DATA_API_KEY", default="")
        if not api_key:
            raise CommandError("No API key. Pass --api-key or set SAMPLE_DATA_API_KEY.")

        machines = self._fetch(base_url, api_key)
        models = self._group(machines)
        self.stdout.write(f"Fetched {len(machines)} machines → {len(models)} models.")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: fixture not written."))
            return

        output: Path = options["output"]
        output.write_text(json.dumps(models, indent=2, ensure_ascii=False) + "\n")
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(models)} models to {output}"))

    def _fetch(self, base_url: str, api_key: str) -> list[dict[str, Any]]:
        url = f"{base_url}/api/v1/machines/"
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise CommandError(f"Failed to fetch {url}: {exc}") from exc
        except ValueError as exc:  # includes json.JSONDecodeError
            raise CommandError(f"Invalid JSON from {url}: {exc}") from exc

        machines = payload.get("machines") if isinstance(payload, dict) else None
        if not isinstance(machines, list):
            raise CommandError(f"Unexpected response from {url}: missing 'machines' list.")
        # Validate each entry at the boundary so _group can trust the shape.
        for entry in machines:
            if not isinstance(entry, dict) or not isinstance(entry.get("model"), dict):
                raise CommandError(f"Unexpected machine entry from {url}: {entry!r}")
        return machines

    def _group(self, machines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Regroup the API's flat instance list into the per-model fixture shape."""
        grouped: dict[Any, dict[str, Any]] = {}
        for machine in machines:
            model = machine.get("model", {})
            # Group by IPDB id when present (stable), else fall back to the name.
            key = (
                ("ipdb", model["ipdb_id"]) if model.get("ipdb_id") else ("name", model.get("name"))
            )
            grouped.setdefault(key, {"model": model, "instances": []})["instances"].append(machine)

        entries: list[dict[str, Any]] = []
        for bucket in grouped.values():
            model = bucket["model"]
            entry = {
                field: model[field]
                for field in MODEL_FIELD_ORDER
                if model.get(field) not in (None, "")
            }
            entry["instances"] = [
                self._instance_entry(inst, model.get("name"))
                for inst in sorted(bucket["instances"], key=lambda i: i.get("name") or "")
            ]
            entries.append(entry)

        # Chronological, diff-friendly ordering matching the existing fixture.
        entries.sort(key=lambda e: (e.get("year") or 0, e.get("name") or ""))
        return entries

    def _instance_entry(self, inst: dict[str, Any], model_name: str | None) -> dict[str, Any]:
        entry: dict[str, Any] = {}
        # Keep the instance name only when it differs from the model name, so
        # single-instance models stay terse and multi-instance ones stay unique.
        if inst.get("name") and inst["name"] != model_name:
            entry["name"] = inst["name"]
        if inst.get("short_name"):
            entry["short_name"] = inst["short_name"]
        if inst.get("serial_number"):
            entry["serial_number"] = inst["serial_number"]
        entry["operational_status"] = inst.get("operational_status")
        if inst.get("location"):
            entry["location"] = inst["location"]
        return entry
