"""Webhook handler for log entry records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from flipfix.apps.core.markdown_links import render_all_links
from flipfix.apps.discord.formatters import (
    build_discord_embed,
    get_base_url,
    get_maintainer_display_name,
    summarize,
)
from flipfix.apps.discord.webhook_handlers import WebhookHandler, register
from flipfix.apps.maintenance import auto_log
from flipfix.apps.maintenance.models import ProblemReport

if TYPE_CHECKING:
    from flipfix.apps.maintenance.models import LogEntry


class LogEntryWebhookHandler(WebhookHandler):
    name = "log_entry"
    event_type = "log_entry_created"
    model_path = "maintenance.LogEntry"
    display_name = "Log Entry"
    emoji = "🗒️"
    color = 3447003  # Blue
    select_related = ("machine", "problem_report", "created_by", "created_by__maintainer")
    prefetch_related = ("maintainers", "maintainers__discord_link")

    def get_detail_url(self, obj: LogEntry) -> str:
        return reverse("log-detail", kwargs={"pk": obj.pk})

    def get_submitting_user(self, obj: LogEntry):
        # Log entries record their creator directly, so no history lookup is needed.
        return obj.created_by or super().get_submitting_user(obj)

    def get_machine(self, obj: LogEntry):
        return obj.machine

    def is_substantive(self, obj: LogEntry) -> bool:
        """A log entry counts unless Flipfix wrote it (status change, close, …)."""
        return auto_log.classify(obj.text) is None

    def get_summary_line(self, obj: LogEntry) -> str:
        """One line for this entry inside somebody else's post.

        For a close/re-open the entry's own text ("Closed problem report") says
        nothing about *which* report, so name the report instead.
        """
        text = render_all_links(obj.text, plain_text=True)
        if obj.problem_report and auto_log.classify(obj.text) is not None:
            return f"{text}: {_problem_report_summary(obj.problem_report)}"
        return text

    def get_sweep_label(self, obj: LogEntry) -> str:
        recognised = auto_log.classify(obj.text)
        return recognised.action_label if recognised else "Logged"

    def format_webhook_message(
        self,
        obj: LogEntry,
        *,
        followups: list[str] | None = None,
        photos: list | None = None,
    ) -> dict:
        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Build linked_record if attached to a problem report
        linked_record = None
        if obj.problem_report:
            pr = obj.problem_report
            pr_url = base_url + reverse("problem-report-detail", kwargs={"pk": pr.pk})
            pr_text = _problem_report_summary(pr)
            # Format: 📎 Problem Report #N: [text] (hyperlink the #N)
            if pr_text:
                linked_record = f"📎 [Problem Report #{pr.pk}]({pr_url}): {pr_text}"
            else:
                linked_record = f"📎 [Problem Report #{pr.pk}]({pr_url})"

        # Get maintainer names (from explicit maintainers or fall back to created_by)
        maintainer_names: list[str] = []
        for m in obj.maintainers.all():
            maintainer_names.append(get_maintainer_display_name(m))
        if obj.maintainer_names:
            maintainer_names.append(obj.maintainer_names)

        # Fall back to created_by for auto-generated log entries
        if not maintainer_names and obj.created_by:
            # Check if created_by has a maintainer profile with discord link
            maintainer = getattr(obj.created_by, "maintainer", None)
            if maintainer:
                maintainer_names.append(get_maintainer_display_name(maintainer))
            else:
                maintainer_names.append(obj.created_by.get_full_name() or obj.created_by.username)

        user_attribution = ", ".join(maintainer_names) if maintainer_names else "Unknown"

        return build_discord_embed(
            title=f"{self.emoji} {obj.machine.short_display_name}",
            title_url=url,
            record_description=render_all_links(obj.text, base_url=base_url),
            user_attribution=user_attribution,
            color=self.color,
            photos=self.get_photos(obj) if photos is None else photos,
            base_url=base_url,
            linked_record=linked_record,
            followups=followups,
        )


def _problem_report_summary(report: ProblemReport) -> str:
    """ "[problem type]: [short description]" for a linked report."""
    parts: list[str] = []
    if report.problem_type != ProblemReport.ProblemType.OTHER:
        parts.append(report.get_problem_type_display())
    if report.description:
        parts.append(summarize(render_all_links(report.description, plain_text=True)))
    return ": ".join(parts)


register(LogEntryWebhookHandler())
