"""Webhook handler for problem report records."""

from __future__ import annotations

from django.urls import reverse

from flipfix.apps.core.markdown_links import render_all_links
from flipfix.apps.discord.formatters import build_discord_embed, get_base_url
from flipfix.apps.discord.webhook_handlers import WebhookHandler, register
from flipfix.apps.maintenance.models import ProblemReport


class ProblemReportWebhookHandler(WebhookHandler):
    name = "problem_report"
    event_type = "problem_report_created"
    model_path = "maintenance.ProblemReport"
    display_name = "Problem Report"
    emoji = "⚠️"
    color = 15158332  # Red
    select_related = ("machine", "reported_by_user")

    def get_detail_url(self, obj: ProblemReport) -> str:
        return reverse("problem-report-detail", kwargs={"pk": obj.pk})

    def get_attributed_user(self, obj: ProblemReport):
        return obj.reported_by_user

    def get_machine(self, obj: ProblemReport):
        return obj.machine

    def get_summary_line(self, obj: ProblemReport) -> str:
        return self._describe(obj, plain_text=True) or "Problem report"

    def get_sweep_label(self, obj: ProblemReport) -> str:
        return "Reported"

    def format_webhook_message(
        self,
        obj: ProblemReport,
        *,
        followups: list[str] | None = None,
        photos: list | None = None,
    ) -> dict:
        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        return build_discord_embed(
            title=f"{self.emoji} {obj.machine.short_display_name}",
            title_url=url,
            record_description=self._describe(obj, base_url=base_url),
            user_attribution=obj.reporter_display,
            color=self.color,
            photos=self.get_photos(obj) if photos is None else photos,
            base_url=base_url,
            followups=followups,
        )

    def _describe(self, obj: ProblemReport, *, base_url: str = "", plain_text: bool = False) -> str:
        """Build "[problem type]: [description]", omitting the type when it's Other."""
        parts: list[str] = []
        if obj.problem_type != ProblemReport.ProblemType.OTHER:
            parts.append(obj.get_problem_type_display())
        if obj.description:
            parts.append(
                render_all_links(obj.description, plain_text=True)
                if plain_text
                else render_all_links(obj.description, base_url=base_url)
            )
        return ": ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")


register(ProblemReportWebhookHandler())
