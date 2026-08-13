"""Webhook handler for part request update records."""

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
from flipfix.apps.parts.status_log import status_change_comment

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

    def get_attributed_user(self, obj: PartRequestUpdate):
        return obj.posted_by.user if obj.posted_by else None

    def get_machine(self, obj: PartRequestUpdate):
        return obj.part_request.machine

    def is_substantive(self, obj: PartRequestUpdate) -> bool:
        """A bare status flip is bookkeeping; a status flip plus a note is not."""
        return bool(status_change_comment(obj.text))

    def get_summary_line(self, obj: PartRequestUpdate) -> str:
        # Name the part being discussed — the update's own text is often an
        # auto-generated "Status changed: …" that says nothing about the part.
        part = part_name(obj.part_request.text)
        comment = status_change_comment(obj.text) if obj.new_status else obj.text
        comment = " ".join(render_all_links(comment, plain_text=True).split())
        if obj.new_status:
            marked = f"Marked {obj.get_new_status_display()}: {part}"
            return f"{marked} — {comment}" if comment else marked
        return f"{part}: {comment}"

    def get_sweep_label(self, obj: PartRequestUpdate) -> str:
        return f"Marked {obj.get_new_status_display()}" if obj.new_status else "Commented on"

    def get_sweep_entry(self, obj: PartRequestUpdate) -> str:
        return part_name(obj.part_request.text)

    def format_webhook_message(
        self,
        obj: PartRequestUpdate,
        *,
        followups: list[str] | None = None,
        photos: list | None = None,
    ) -> dict:
        base_url = get_base_url()
        url = base_url + self.get_detail_url(obj)

        # Build linked_record for the parent parts request
        pr = obj.part_request
        linked_record = f"📎 [Parts Request #{pr.pk}]({url}): {part_name(pr.text)}"

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

        return build_discord_embed(
            title=title,
            title_url=url,
            record_description=render_all_links(obj.text, base_url=base_url),
            user_attribution=user_attribution,
            color=self.color,
            photos=self.get_photos(obj) if photos is None else photos,
            base_url=base_url,
            linked_record=linked_record,
            followups=followups,
        )


register(PartRequestUpdateWebhookHandler())
