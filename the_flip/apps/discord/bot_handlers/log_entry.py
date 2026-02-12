"""Bot handler for creating log entry records from Discord."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.bot_handlers import BotRecordHandler, register

if TYPE_CHECKING:
    from the_flip.apps.accounts.models import Maintainer
    from the_flip.apps.catalog.models import MachineInstance
    from the_flip.apps.maintenance.models import LogEntry

logger = logging.getLogger(__name__)


class LogEntryBotHandler(BotRecordHandler):
    name = "log_entry"
    display_name = "Log Entry"
    machine_required = True
    parent_handler_name = "problem_report"
    child_type_name = None
    media_model_name = "LogEntryMedia"
    url_pattern = re.compile(r"/logs/(\d+)$")

    def create_from_suggestion(
        self,
        *,
        description: str,
        machine: MachineInstance | None,
        maintainer: Maintainer | None,
        display_name: str,
        parent_record_id: int | None,
        occurred_at: datetime,
    ) -> LogEntry:
        from the_flip.apps.maintenance.models import LogEntry, ProblemReport

        # If no machine specified but has parent_record_id, inherit machine from parent
        if not machine and parent_record_id:
            parent_report = ProblemReport.objects.filter(pk=parent_record_id).first()
            if parent_report:
                machine = parent_report.machine

        if not machine:
            raise ValueError("Machine is required for log_entry")

        fallback_name = display_name or "Discord"

        # Look up parent problem report if specified
        problem_report = None
        if parent_record_id:
            problem_report = ProblemReport.objects.filter(pk=parent_record_id).first()
            if not problem_report:
                logger.warning(
                    "discord_parent_problem_report_not_found",
                    extra={"parent_record_id": parent_record_id},
                )

        log_entry = LogEntry.objects.create(
            machine=machine,
            text=description,
            maintainer_names="" if maintainer else fallback_name,
            problem_report=problem_report,
            occurred_at=occurred_at,
        )

        if maintainer:
            log_entry.maintainers.add(maintainer)

        return log_entry

    def get_detail_url(self, obj: LogEntry) -> str:
        return reverse("log-detail", kwargs={"pk": obj.pk})


register(LogEntryBotHandler())
