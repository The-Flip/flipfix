"""Webhook handler for log entry records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.formatters import (
    build_discord_embed,
    get_base_url,
    get_maintainer_display_name,
)
from the_flip.apps.discord.webhook_handlers import WebhookHandler, register
from the_flip.apps.maintenance.models import ProblemReport

if TYPE_CHECKING:
    from the_flip.apps.maintenance.models import LogEntry


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

    def format_webhook_message(self, obj: LogEntry) -> dict:
        from the_flip.apps.maintenance.models import LogEntryMedia

        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Build linked_record if attached to a problem report
        linked_record = None
        if obj.problem_report:
            pr = obj.problem_report
            pr_url = base_url + reverse("problem-report-detail", kwargs={"pk": pr.pk})
            # Build PR text: [problem type]: [truncated description]
            pr_text_parts: list[str] = []
            if pr.problem_type != ProblemReport.ProblemType.OTHER:
                pr_text_parts.append(pr.get_problem_type_display())
            if pr.description:
                pr_desc = pr.description[:50]
                if len(pr.description) > 50:
                    pr_desc += "..."
                pr_text_parts.append(pr_desc)
            pr_text = ": ".join(pr_text_parts) if pr_text_parts else ""
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

        # Get photos with thumbnails (up to 4 for Discord gallery)
        photos = list(
            obj.media.filter(media_type=LogEntryMedia.MediaType.PHOTO)  # type: ignore[attr-defined]
            .filter(thumbnail_file__gt="")
            .order_by("display_order", "created_at")[:4]
        )

        return build_discord_embed(
            title=f"{self.emoji} {obj.machine.short_display_name}",
            title_url=url,
            record_description=obj.text,
            user_attribution=user_attribution,
            color=self.color,
            photos=photos,
            base_url=base_url,
            linked_record=linked_record,
        )


register(LogEntryWebhookHandler())
