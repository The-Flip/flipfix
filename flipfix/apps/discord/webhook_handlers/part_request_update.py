"""Webhook handler for part request update records."""

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
    from flipfix.apps.parts.models import PartRequestUpdate


class PartRequestUpdateWebhookHandler(WebhookHandler):
    name = "part_request_update"
    event_type = "part_request_update_created"
    model_path = "parts.PartRequestUpdate"
    display_name = "Parts Request Update"
    emoji = "💬"
    color = 3447003  # Blue
    select_related = (
        "part_request__machine",
        "posted_by__user",
        "posted_by__discord_link",
    )

    def get_detail_url(self, obj: PartRequestUpdate) -> str:
        return reverse("part-request-detail", kwargs={"pk": obj.part_request.pk})

    def get_actor_user(self, obj: PartRequestUpdate):
        return obj.posted_by.user if obj.posted_by else None

    def get_machine(self, obj: PartRequestUpdate):
        return obj.part_request.machine

    def get_digest_text(self, obj: PartRequestUpdate) -> str:
        # Name the part being discussed (the update's own text is often an
        # auto-generated "Status changed: …" that says nothing about the part).
        # For a status change, lead with the status so it survives line trimming.
        part = render_all_links(obj.part_request.text, plain_text=True)
        if obj.new_status:
            return f"Marked {obj.get_new_status_display()}: {part}"
        return f"{part}: {render_all_links(obj.text, plain_text=True)}"

    def format_webhook_message(self, obj: PartRequestUpdate) -> dict:
        from flipfix.apps.parts.models import PartRequestUpdateMedia

        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Build linked_record for the parent parts request
        pr = obj.part_request
        rendered_text = render_all_links(pr.text, plain_text=True)
        pr_desc = rendered_text[:50]
        if len(rendered_text) > 50:
            pr_desc += "..."
        linked_record = f"📎 [Parts Request #{pr.pk}]({url}): {pr_desc}"

        # Get user attribution (use Discord name if available, or fall back to display property)
        if obj.posted_by:
            user_attribution = get_maintainer_display_name(obj.posted_by)
        else:
            user_attribution = obj.poster_display or "Unknown"

        # Build title
        if obj.part_request.machine:
            title = (
                f"{self.emoji} Update on Parts Request"
                f" for {obj.part_request.machine.short_display_name}"
            )
        else:
            title = f"{self.emoji} Update on Parts Request"

        # Get photos with thumbnails (up to 4 for Discord gallery)
        photos = list(
            obj.media.filter(media_type=PartRequestUpdateMedia.MediaType.PHOTO)
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
            linked_record=linked_record,
        )


register(PartRequestUpdateWebhookHandler())
