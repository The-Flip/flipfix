"""Webhook handler for part request records."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from flipfix.apps.core.markdown_links import render_all_links
from flipfix.apps.discord.formatters import (
    build_discord_embed,
    get_base_url,
    get_maintainer_display_name,
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

    def get_actor_user(self, obj: PartRequest):
        return obj.requested_by.user if obj.requested_by else None

    def get_machine(self, obj: PartRequest):
        return obj.machine

    def get_digest_text(self, obj: PartRequest) -> str:
        return f"Parts request: {render_all_links(obj.text, plain_text=True)}"

    def format_webhook_message(self, obj: PartRequest) -> dict:
        from flipfix.apps.parts.models import PartRequestMedia

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

        # Get photos with thumbnails (up to 4 for Discord gallery)
        photos = list(
            obj.media.filter(media_type=PartRequestMedia.MediaType.PHOTO)
            .filter(thumbnail_file__gt="")
            .order_by("display_order", "created_at")[:4]
        )

        return build_discord_embed(
            title=title,
            title_url=url,
            record_description=render_all_links(obj.text, base_url=base_url),
            user_attribution=user_attribution,
            color=self.color,
            photos=photos,
            base_url=base_url,
        )


register(PartRequestWebhookHandler())
