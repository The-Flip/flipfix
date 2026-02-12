"""Webhook handler for problem report records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from the_flip.apps.discord.formatters import build_discord_embed, get_base_url
from the_flip.apps.discord.webhook_handlers import WebhookHandler, register

if TYPE_CHECKING:
    from the_flip.apps.maintenance.models import ProblemReport


class ProblemReportWebhookHandler(WebhookHandler):
    name = "problem_report"
    event_type = "problem_report_created"
    model_path = "maintenance.ProblemReport"
    display_name = "Problem Report"
    emoji = "⚠️"
    color = 15158332  # Red
    select_related = ("machine",)

    def get_detail_url(self, obj: ProblemReport) -> str:
        return reverse("problem-report-detail", kwargs={"pk": obj.pk})

    def format_webhook_message(self, obj: ProblemReport) -> dict:
        from the_flip.apps.maintenance.models import ProblemReportMedia

        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Build description: [problem type]: [description] (omit type if "Other")
        parts: list[str] = []
        if obj.problem_type != "other":
            parts.append(obj.get_problem_type_display())
        if obj.description:
            parts.append(obj.description)

        record_description = ": ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")

        # Get photos with thumbnails (up to 4 for Discord gallery)
        photos = list(
            obj.media.filter(media_type=ProblemReportMedia.MediaType.PHOTO)
            .filter(thumbnail_file__gt="")
            .order_by("display_order", "created_at")[:4]
        )

        return build_discord_embed(
            title=f"{self.emoji} {obj.machine.short_display_name}",
            title_url=url,
            record_description=record_description,
            user_attribution=obj.reporter_display,
            color=self.color,
            photos=photos,
            base_url=base_url,
        )


register(ProblemReportWebhookHandler())
