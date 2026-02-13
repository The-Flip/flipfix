"""Bot handler for creating part request records from Discord."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.bot_handlers import BotRecordHandler, register

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.parts.models import PartRequest


class PartRequestBotHandler(BotRecordHandler):
    name = "part_request"
    display_name = "Part Request"
    model_path = "parts.PartRequest"
    machine_required = False
    parent_handler_name = None
    child_type_name = "part_request_update"
    media_model_name = "PartRequestMedia"
    url_pattern = re.compile(r"/parts/(\d+)$")

    def create_from_suggestion(
        self,
        *,
        description: str,
        machine: MachineInstance | None,
        maintainer: Maintainer | None,
        display_name: str,
        parent_record_id: int | None,
        occurred_at: datetime,
    ) -> PartRequest:
        from the_flip.apps.parts.models import PartRequest

        if not maintainer:
            raise ValueError("Cannot create part request without a linked maintainer")

        return PartRequest.objects.create(
            machine=machine,
            text=description,
            requested_by=maintainer,
            occurred_at=occurred_at,
        )

    def get_detail_url(self, obj: PartRequest) -> str:
        return reverse("part-request-detail", kwargs={"pk": obj.pk})


register(PartRequestBotHandler())
