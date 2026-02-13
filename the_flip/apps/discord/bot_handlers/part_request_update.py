"""Bot handler for creating part request update records from Discord."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.bot_handlers import BotRecordHandler, register

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.parts.models import PartRequestUpdate


class PartRequestUpdateBotHandler(BotRecordHandler):
    name = "part_request_update"
    display_name = "Part Request Update"
    model_path = "parts.PartRequestUpdate"
    machine_required = False
    parent_handler_name = "part_request"
    child_type_name = None
    media_model_name = "PartRequestUpdateMedia"
    url_pattern = None  # Updates share parent's URL, no distinct pattern

    def create_from_suggestion(
        self,
        *,
        description: str,
        machine: MachineInstance | None,
        maintainer: Maintainer | None,
        display_name: str,
        parent_record_id: int | None,
        occurred_at: datetime,
    ) -> PartRequestUpdate:
        from the_flip.apps.parts.models import PartRequest, PartRequestUpdate

        if not maintainer:
            raise ValueError("Cannot create part request update without a linked maintainer")

        if not parent_record_id:
            raise ValueError("part_request_update requires parent_record_id")

        part_request = PartRequest.objects.filter(pk=parent_record_id).first()
        if not part_request:
            raise ValueError(f"Part request not found: {parent_record_id}")

        return PartRequestUpdate.objects.create(
            part_request=part_request,
            text=description,
            posted_by=maintainer,
            occurred_at=occurred_at,
        )

    def get_detail_url(self, obj: PartRequestUpdate) -> str:
        # URL points to parent part request (update doesn't have its own page)
        return reverse("part-request-detail", kwargs={"pk": obj.part_request.pk})


register(PartRequestUpdateBotHandler())
