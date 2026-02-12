"""Bot handler for creating problem report records from Discord."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.bot_handlers import BotRecordHandler, register

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.maintenance.models import ProblemReport


class ProblemReportBotHandler(BotRecordHandler):
    name = "problem_report"
    display_name = "Problem Report"
    machine_required = True
    parent_handler_name = None
    child_type_name = "log_entry"
    media_model_name = "ProblemReportMedia"
    url_pattern = re.compile(r"/problem-reports/(\d+)$")

    def create_from_suggestion(
        self,
        *,
        description: str,
        machine: MachineInstance | None,
        maintainer: Maintainer | None,
        display_name: str,
        parent_record_id: int | None,
        occurred_at: datetime,
    ) -> ProblemReport:
        from the_flip.apps.maintenance.models import ProblemReport

        if not machine:
            raise ValueError("Machine is required for problem_report")

        fallback_name = display_name or "Discord"
        return ProblemReport.objects.create(
            machine=machine,
            description=description,
            problem_type=ProblemReport.ProblemType.OTHER,
            reported_by_user=maintainer.user if maintainer else None,
            reported_by_name="" if maintainer else fallback_name,
            occurred_at=occurred_at,
        )

    def get_detail_url(self, obj: ProblemReport) -> str:
        return reverse("problem-report-detail", kwargs={"pk": obj.pk})


register(ProblemReportBotHandler())
