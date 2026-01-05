"""Create sample part requests."""

from __future__ import annotations

import json
import mimetypes
import re
from datetime import datetime
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.catalog.models import MachineInstance
from the_flip.apps.parts.models import (
    PartRequest,
    PartRequestMedia,
    PartRequestUpdate,
    PartRequestUpdateMedia,
)


class Command(BaseCommand):
    help = "Create sample part requests from docs/sample_data/part_requests.json (dev/PR only)"

    data_path = Path("docs/sample_data/records/part_requests.json")
    media_path = Path("docs/sample_data/media/parts")

    def __init__(self):
        super().__init__()
        self.machine_name_mapping = {}
        self.maintainer_name_mapping = {
            self.normalize_name("caleb"): "junkybrassmonkey",
        }

    def handle(self, *args, **options):
        # Safety check: SQLite only (blocks production PostgreSQL)
        if "sqlite" not in connection.settings_dict["ENGINE"].lower():
            raise CommandError(
                "This command only runs on SQLite databases (local dev or PR environments)"
            )

        # Safety check: empty database only
        if PartRequest.objects.exists():
            raise CommandError(
                "Database already contains part requests. "
                "This command only runs on empty databases."
            )

        if not self.data_path.exists():
            raise CommandError(f"Data file not found: {self.data_path}")

        with self.data_path.open() as fh:
            data = json.load(fh)

        self.stdout.write(self.style.SUCCESS("\nCreating sample part requests..."))

        request_count, update_count = self.import_part_requests(data.get("part_requests", []))

        self.stdout.write(
            self.style.SUCCESS(f"Created {request_count} part requests and {update_count} updates.")
        )

    # ---- helpers ---------------------------------------------------------
    @staticmethod
    def normalize_name(value: str) -> str:
        if not value:
            return ""
        normalized = re.sub(r"[^\w\s]", "", value.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def find_machine(self, name: str) -> MachineInstance | None:
        target = self.normalize_name(name)
        if not target:
            return None
        machines = MachineInstance.objects.all()
        for machine in machines:
            if self.normalize_name(machine.name) == target:
                return machine
            if machine.short_name and self.normalize_name(machine.short_name) == target:
                return machine
        mapped_name = self.machine_name_mapping.get(target)
        if mapped_name:
            mapped_target = self.normalize_name(mapped_name)
            for machine in machines:
                if self.normalize_name(machine.name) == mapped_target:
                    return machine
        return MachineInstance.objects.filter(slug=name).first()

    def find_maintainer(self, name: str) -> Maintainer | None:
        target = self.normalize_name(name)
        if not target:
            return None
        if target in self.maintainer_name_mapping:
            target = self.normalize_name(self.maintainer_name_mapping[target])
        for maintainer in Maintainer.objects.select_related("user"):
            username = self.normalize_name(maintainer.user.username)
            first = self.normalize_name(maintainer.user.first_name or "")
            last = self.normalize_name(maintainer.user.last_name or "")
            full = self.normalize_name(
                f"{maintainer.user.first_name} {maintainer.user.last_name}".strip()
            )
            if target in {username, first, last, full}:
                return maintainer
        return None

    @staticmethod
    def parse_iso_datetime(raw: str) -> datetime:
        if not raw:
            return timezone.now()
        try:
            # Parse ISO format datetime
            dt = datetime.fromisoformat(raw)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except ValueError:
            return timezone.now()

    def _create_media_attachments(
        self,
        media_filenames: list[str],
        parent: PartRequest | PartRequestUpdate,
    ) -> int:
        """Create media attachments for a part request or update.

        Returns the number of media files successfully attached.
        Raises CommandError if any media file is not found.
        """
        if not media_filenames:
            return 0

        created = 0
        for filename in media_filenames:
            file_path = self.media_path / filename
            if not file_path.exists():
                raise CommandError(f"Media file not found: {file_path}")

            # Determine content type from extension
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = "application/octet-stream"

            # Read file and create SimpleUploadedFile
            with file_path.open("rb") as f:
                content = f.read()

            uploaded_file = SimpleUploadedFile(
                name=filename,
                content=content,
                content_type=content_type,
            )

            # Create the appropriate media record
            if isinstance(parent, PartRequest):
                PartRequestMedia.objects.create(
                    part_request=parent,
                    media_type=PartRequestMedia.MediaType.PHOTO,
                    file=uploaded_file,
                )
            else:
                PartRequestUpdateMedia.objects.create(
                    update=parent,
                    media_type=PartRequestUpdateMedia.MediaType.PHOTO,
                    file=uploaded_file,
                )

            created += 1

        return created

    # ---- importers -------------------------------------------------------
    def import_part_requests(self, requests_data: list) -> tuple[int, int]:
        """Import part requests with nested updates. Returns (request_count, update_count)."""
        created_requests = 0
        created_updates = 0
        request_summaries: list[str] = []

        for request_entry in requests_data:
            machine_name = request_entry.get("machine", "").strip()
            text = request_entry.get("text", "").strip()
            if not text:
                self.stdout.write(self.style.WARNING("  Skipping part request missing text."))
                continue

            # Find machine (optional for part requests)
            machine = self.find_machine(machine_name) if machine_name else None
            if machine_name and not machine:
                raise CommandError(
                    f"Machine not found: '{machine_name}'. "
                    "Run create_sample_machines first or fix part_requests.json."
                )

            # Find requester
            requester_name = request_entry.get("requested_by", "").strip()
            requester = self.find_maintainer(requester_name) if requester_name else None

            # Determine status
            status_str = request_entry.get("status", "requested").lower()
            status_map = {
                "requested": PartRequest.Status.REQUESTED,
                "ordered": PartRequest.Status.ORDERED,
                "received": PartRequest.Status.RECEIVED,
                "installed": PartRequest.Status.RECEIVED,  # Map 'installed' to 'received'
                "cancelled": PartRequest.Status.CANCELLED,
            }
            status = status_map.get(status_str, PartRequest.Status.REQUESTED)

            occurred_at = self.parse_iso_datetime(request_entry.get("occurred_at", ""))

            part_request = PartRequest.objects.create(
                machine=machine,
                text=text,
                status=status,
                requested_by=requester,
                requested_by_name=requester_name if not requester else "",
                occurred_at=occurred_at,
            )
            created_requests += 1

            # Attach media if any
            media_filenames = request_entry.get("media", [])
            self._create_media_attachments(media_filenames, part_request)

            # Create updates if any
            update_count = 0
            for update_data in request_entry.get("updates", []):
                update_created = self._create_update(update_data, part_request)
                if update_created:
                    created_updates += 1
                    update_count += 1

            # Build summary for this request
            if machine:
                display_name = machine.short_name or machine.name
            else:
                display_name = "no machine"
            if update_count == 0:
                request_summaries.append(display_name)
            elif update_count == 1:
                request_summaries.append(f"{display_name} (1 update)")
            else:
                request_summaries.append(f"{display_name} ({update_count} updates)")

        if request_summaries:
            self.stdout.write(f"  Part requests: {', '.join(request_summaries)}")

        return created_requests, created_updates

    def _create_update(
        self,
        data: dict,
        part_request: PartRequest,
    ) -> PartRequestUpdate | None:
        """Create a single part request update from JSON data."""
        text = data.get("text", "").strip()
        if not text:
            self.stdout.write(self.style.WARNING("Skipping update missing text."))
            return None

        occurred_at = self.parse_iso_datetime(data.get("occurred_at", ""))
        poster_name = data.get("posted_by", "").strip()
        poster = self.find_maintainer(poster_name) if poster_name else None

        # Determine new_status if provided
        new_status_str = data.get("new_status", "").lower()
        status_map = {
            "requested": PartRequest.Status.REQUESTED,
            "ordered": PartRequest.Status.ORDERED,
            "received": PartRequest.Status.RECEIVED,
            "installed": PartRequest.Status.RECEIVED,  # Map 'installed' to 'received'
            "cancelled": PartRequest.Status.CANCELLED,
        }
        new_status = status_map.get(new_status_str, "")

        update = PartRequestUpdate.objects.create(
            part_request=part_request,
            text=text,
            posted_by=poster,
            posted_by_name=poster_name if not poster else "",
            new_status=new_status,
            occurred_at=occurred_at,
        )

        # Attach media if any
        media_filenames = data.get("media", [])
        self._create_media_attachments(media_filenames, update)

        return update
