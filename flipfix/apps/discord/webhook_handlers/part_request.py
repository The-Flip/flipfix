"""Webhook handler for part request records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from flipfix.apps.core.markdown_links import render_all_links
from flipfix.apps.discord.formatters import (
    build_discord_embed,
    get_base_url,
    get_maintainer_display_name,
    part_name,
)
from flipfix.apps.discord.webhook_handlers import WebhookHandler, register

if TYPE_CHECKING:
    from flipfix.apps.parts.models import PartRequest


class PartRequestWebhookHandler(WebhookHandler):
    name = "part_request"
    event_type = "part_request_created"
    model_path = "parts.PartRequest"
    display_name = "Parts Request"
    emoji = "📦"
    color = 3447003  # Blue
    select_related = ("machine", "requested_by__user", "requested_by__discord_link")

    def get_detail_url(self, obj: PartRequest) -> str:
        return reverse("part-request-detail", kwargs={"pk": obj.pk})

    def get_attributed_user(self, obj: PartRequest):
        return obj.requested_by.user if obj.requested_by else None

    def get_machine(self, obj: PartRequest):
        return obj.machine

    def get_summary_line(self, obj: PartRequest) -> str:
        return f"Parts request: {part_name(obj.text)}"

    def get_sweep_label(self, obj: PartRequest) -> str:
        return "Requested"

    def get_sweep_entry(self, obj: PartRequest) -> str:
        return part_name(obj.text)

    def format_webhook_message(
        self,
        obj: PartRequest,
        *,
        followups: list[str] | None = None,
        photos: list | None = None,
    ) -> dict:
        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Get user attribution (use Discord name if available, or fall back to display property)
        if obj.requested_by:
            user_attribution = get_maintainer_display_name(obj.requested_by)
        else:
            user_attribution = obj.requester_display or "Unknown"

        # Build title with machine name if available
        if obj.machine:
            title = f"{self.emoji} Parts Request for {obj.machine.short_display_name}"
        else:
            title = f"{self.emoji} Parts Request"

        return build_discord_embed(
            title=title,
            title_url=url,
            record_description=render_all_links(obj.text, base_url=base_url),
            user_attribution=user_attribution,
            color=self.color,
            photos=self.get_photos(obj) if photos is None else photos,
            base_url=base_url,
            followups=followups,
        )


register(PartRequestWebhookHandler())
