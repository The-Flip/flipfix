"""Tests for Discord message formatting."""

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings, tag

from flipfix.apps.accounts.models import Maintainer
from flipfix.apps.core.test_utils import (
    TemporaryMediaMixin,
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
    create_problem_report,
)
from flipfix.apps.discord.formatters import (
    DISCORD_POST_DESCRIPTION_MAX_CHARS,
    NOTIFICATION_BODY_MAX_WORDS,
    format_test_message,
    get_base_url,
)
from flipfix.apps.discord.models import DiscordUserLink
from flipfix.apps.maintenance.models import LogEntryMedia


def format_discord_message(event_type, obj):
    """Test helper: format a Discord webhook message for the given event and object."""
    from flipfix.apps.discord.webhook_handlers import get_webhook_handler_by_event

    handler = get_webhook_handler_by_event(event_type)
    if handler:
        return handler.format_webhook_message(obj)
    return {}


@tag("tasks")
class DiscordFormatterTests(TemporaryMediaMixin, TestCase):
    """Tests for Discord message formatting.

    These tests verify the structure of webhook messages, not exact wording.
    This makes them resilient to copy changes.
    """

    def setUp(self):
        self.machine = create_machine()
        self.maintainer_user = create_maintainer_user()

    def test_format_problem_report_created(self):
        """Format a new problem report message."""
        report = create_problem_report(machine=self.machine)
        message = format_discord_message("problem_report_created", report)

        # Verify structure
        self.assertIn("embeds", message)
        self.assertEqual(len(message["embeds"]), 1)
        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.name, embed["title"])

        # URL points to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["url"])

    def test_format_problem_report_with_photos(self):
        """Format a problem report with photos creates multiple embeds for gallery."""
        from flipfix.apps.maintenance.models import ProblemReportMedia

        report = create_problem_report(machine=self.machine)

        # Create mock photos with thumbnails (Discord uses thumbnails, not originals)
        for i in range(3):
            media = ProblemReportMedia(
                problem_report=report,
                media_type=ProblemReportMedia.MediaType.PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=False)
            media.thumbnail_file.save(
                f"test{i}_thumb.jpg", ContentFile(b"fake thumbnail"), save=True
            )

        message = format_discord_message("problem_report_created", report)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # Image URLs should use thumbnail_file, not file
        self.assertIn("_thumb", message["embeds"][0]["image"]["url"])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_problem_report_excludes_photos_without_thumbnails(self):
        """Photos without thumbnails are excluded from Discord gallery."""
        from flipfix.apps.maintenance.models import ProblemReportMedia

        report = create_problem_report(machine=self.machine)

        # Create a photo WITH thumbnail
        media_with_thumb = ProblemReportMedia(
            problem_report=report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            display_order=0,
        )
        media_with_thumb.file.save("with_thumb.jpg", ContentFile(b"fake"), save=False)
        media_with_thumb.thumbnail_file.save("thumb.jpg", ContentFile(b"fake"), save=True)

        # Create a photo with NULL thumbnail
        media_null_thumb = ProblemReportMedia(
            problem_report=report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            display_order=1,
            thumbnail_file=None,
        )
        media_null_thumb.file.save("null_thumb.jpg", ContentFile(b"fake"), save=True)

        # Create a photo with empty string thumbnail (legacy representation)
        media_empty_thumb = ProblemReportMedia(
            problem_report=report,
            media_type=ProblemReportMedia.MediaType.PHOTO,
            display_order=2,
        )
        media_empty_thumb.file.save("empty_thumb.jpg", ContentFile(b"fake"), save=True)
        # thumbnail_file defaults to empty string when not set

        message = format_discord_message("problem_report_created", report)

        # Should only have 1 embed (the photo with thumbnail)
        self.assertEqual(len(message["embeds"]), 1)
        self.assertIn("image", message["embeds"][0])

    def test_format_log_entry_created(self):
        """Format a new log entry message."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.maintainer_user)
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.name, embed["title"])

        # Description includes log text
        self.assertIn(log_entry.text, embed["description"])

        # URL points to the log entry
        self.assertIn(f"/logs/{log_entry.pk}/", embed["url"])

    def test_format_log_entry_with_problem_report(self):
        """Format a log entry attached to a problem report includes PR link."""
        report = create_problem_report(machine=self.machine)
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            problem_report=report,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Description includes link to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["description"])

    def test_format_log_entry_with_photos(self):
        """Format a log entry with photos creates multiple embeds for gallery."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.maintainer_user)

        # Create mock photos with thumbnails (Discord uses thumbnails, not originals)
        for i in range(3):
            media = LogEntryMedia(
                log_entry=log_entry,
                media_type=LogEntryMedia.MediaType.PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=False)
            media.thumbnail_file.save(
                f"test{i}_thumb.jpg", ContentFile(b"fake thumbnail"), save=True
            )

        message = format_discord_message("log_entry_created", log_entry)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # Image URLs should use thumbnail_file, not file
        self.assertIn("_thumb", message["embeds"][0]["image"]["url"])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_log_entry_excludes_photos_without_thumbnails(self):
        """Photos without thumbnails are excluded from Discord gallery."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.maintainer_user)

        # Create a photo WITH thumbnail
        media_with_thumb = LogEntryMedia(
            log_entry=log_entry,
            media_type=LogEntryMedia.MediaType.PHOTO,
            display_order=0,
        )
        media_with_thumb.file.save("with_thumb.jpg", ContentFile(b"fake"), save=False)
        media_with_thumb.thumbnail_file.save("thumb.jpg", ContentFile(b"fake"), save=True)

        # Create a photo with NULL thumbnail
        media_null_thumb = LogEntryMedia(
            log_entry=log_entry,
            media_type=LogEntryMedia.MediaType.PHOTO,
            display_order=1,
            thumbnail_file=None,
        )
        media_null_thumb.file.save("null_thumb.jpg", ContentFile(b"fake"), save=True)

        message = format_discord_message("log_entry_created", log_entry)

        # Should only have 1 embed (the photo with thumbnail)
        self.assertEqual(len(message["embeds"]), 1)
        self.assertIn("image", message["embeds"][0])

    def test_format_log_entry_uses_discord_name_when_linked(self):
        """Log entry uses Discord display name when maintainer is linked."""
        maintainer = Maintainer.objects.get(user=self.maintainer_user)

        # Create Discord link
        DiscordUserLink.objects.create(
            discord_user_id="123456789",
            discord_username="discorduser",
            discord_display_name="Discord Display Name",
            maintainer=maintainer,
        )

        log_entry = create_log_entry(machine=self.machine, created_by=self.maintainer_user)
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Description should include the Discord display name
        self.assertIn("Discord Display Name", embed["description"])

    def test_log_entry_no_truncation_when_under_limit(self):
        """Log entry with ~3000 char description is not truncated."""
        # Create a log entry with a long but under-limit description
        long_text = "A" * 3000
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            text=long_text,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Full text should appear without truncation ellipsis
        self.assertIn(long_text, embed["description"])
        # The description should not end with "..." from truncation
        # (it may have "— Username" at the end, which is fine)
        self.assertNotIn("AAA...", embed["description"])

    def test_log_entry_capped_to_a_couple_hundred_words(self):
        """A long multi-word entry (e.g. a pasted checklist) is capped, not dumped."""
        long_text = " ".join(f"word{i}" for i in range(500))
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            text=long_text,
        )
        message = format_discord_message("log_entry_created", log_entry)
        description = message["embeds"][0]["description"]

        self.assertIn("…", description)
        self.assertIn("word0 ", description)  # the head is kept
        # Pin the boundary: the last kept word (index MAX-1) stays as the cut
        # point, the next word (index MAX) is dropped.
        self.assertIn(f"word{NOTIFICATION_BODY_MAX_WORDS - 1}…", description)
        self.assertNotIn(f"word{NOTIFICATION_BODY_MAX_WORDS}", description)
        self.assertNotIn("word499", description)  # the tail was dropped
        # Body is capped near the limit (attribution adds a couple of words).
        self.assertLessEqual(len(description.split()), NOTIFICATION_BODY_MAX_WORDS + 5)

    def test_log_entry_truncates_description_preserving_attribution(self):
        """Log entry with 5000+ char description truncates but preserves user attribution."""
        # Create a log entry that exceeds Discord's limit
        long_text = "B" * 5000
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            text=long_text,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]
        description = embed["description"]

        # Total length should be under Discord's limit (with safety margin)
        self.assertLess(len(description), DISCORD_POST_DESCRIPTION_MAX_CHARS)

        # User attribution should be preserved at the end
        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.assertTrue(
            description.endswith(f"— {maintainer.display_name}"),
            f"Description should end with user attribution, got: ...{description[-50:]}",
        )

        # The record description should be truncated (has ellipsis)
        self.assertIn("...", description)

    def test_log_entry_truncates_preserving_linked_record(self):
        """Log entry with long description AND problem report preserves both suffix parts."""
        # Create a problem report to link
        report = create_problem_report(machine=self.machine)

        # Create a log entry with very long text
        long_text = "C" * 5000
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            text=long_text,
            problem_report=report,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]
        description = embed["description"]

        # Total length should be under Discord's limit
        self.assertLess(len(description), DISCORD_POST_DESCRIPTION_MAX_CHARS)

        # Linked problem report should be preserved
        self.assertIn(f"Problem Report #{report.pk}", description)

        # User attribution should be preserved at the end
        maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.assertTrue(
            description.endswith(f"— {maintainer.display_name}"),
            f"Description should end with user attribution, got: ...{description[-50:]}",
        )

        # The record description should be truncated (has ellipsis before the linked record)
        self.assertIn("...", description)

    def test_format_test_message(self):
        """Format a test message has required structure."""
        message = format_test_message("problem_report_created")

        self.assertIn("embeds", message)
        embed = message["embeds"][0]
        self.assertIn("title", embed)
        self.assertIn("description", embed)

    @override_settings(SITE_URL="https://example.com")
    def test_format_log_entry_renders_record_links(self):
        """Log entry text with [[type:ref]] links renders as clickable Discord links."""
        # Create a second machine to reference in the text
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            text=f"Fixed it. See [[machine:id:{ref_machine.pk}]] for related issue.",
        )
        message = format_discord_message("log_entry_created", log_entry)

        description = message["embeds"][0]["description"]

        # Link should be rendered with absolute URL
        self.assertIn("Attack From Mars", description)
        self.assertIn("https://example.com/machines/attack-from-mars/", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)

    @override_settings(SITE_URL="https://example.com")
    def test_format_log_entry_renders_links_in_linked_record_preview(self):
        """Linked PR preview renders [[type:ref]] as plain text labels."""
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        report = create_problem_report(
            machine=self.machine,
            description=f"See [[machine:id:{ref_machine.pk}]] for context",
        )
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.maintainer_user,
            problem_report=report,
        )
        message = format_discord_message("log_entry_created", log_entry)

        description = message["embeds"][0]["description"]

        # PR preview should contain the machine name as plain text
        self.assertIn("Attack From Mars", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)

    @override_settings(SITE_URL="https://example.com")
    def test_format_problem_report_renders_record_links(self):
        """Problem report description with [[type:ref]] links renders as Discord links."""
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        report = create_problem_report(
            machine=self.machine,
            description=f"Same issue as [[machine:id:{ref_machine.pk}]]",
        )
        message = format_discord_message("problem_report_created", report)

        description = message["embeds"][0]["description"]

        # Link should be rendered with absolute URL
        self.assertIn("Attack From Mars", description)
        self.assertIn("https://example.com/machines/attack-from-mars/", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)


@tag("tasks")
class PartRequestWebhookFormatterTests(TemporaryMediaMixin, TestCase):
    """Tests for part request Discord webhook formatting."""

    def setUp(self):
        self.maintainer_user = create_maintainer_user()
        self.maintainer = Maintainer.objects.get(user=self.maintainer_user)
        self.machine = create_machine()

    def test_format_part_request_created(self):
        """Format a new part request message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        message = format_discord_message("part_request_created", part_request)

        # Verify structure
        self.assertIn("embeds", message)
        self.assertEqual(len(message["embeds"]), 1)
        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.name, embed["title"])

        # Description includes the text
        self.assertIn("flipper rubbers", embed["description"])

        # URL points to the part request
        self.assertIn(f"/parts/{part_request.pk}/", embed["url"])

    def test_format_part_request_update_created(self):
        """Format a part request update message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
        )
        message = format_discord_message("part_request_update_created", update)

        embed = message["embeds"][0]

        # Title includes machine name
        self.assertIn(self.machine.name, embed["title"])

        # Description includes the update text
        self.assertIn("Marco Specialties", embed["description"])

    def test_format_part_request_with_photos(self):
        """Format a part request with photos creates multiple embeds for gallery."""
        from flipfix.apps.parts.models import PartRequestMedia

        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )

        # Create mock photos with thumbnails (Discord uses thumbnails, not originals)
        for i in range(3):
            media = PartRequestMedia(
                part_request=part_request,
                media_type=PartRequestMedia.MediaType.PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=False)
            media.thumbnail_file.save(
                f"test{i}_thumb.jpg", ContentFile(b"fake thumbnail"), save=True
            )

        message = format_discord_message("part_request_created", part_request)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # Image URLs should use thumbnail_file, not file
        self.assertIn("_thumb", message["embeds"][0]["image"]["url"])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_part_request_excludes_photos_without_thumbnails(self):
        """Photos without thumbnails are excluded from Discord gallery."""
        from flipfix.apps.parts.models import PartRequestMedia

        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )

        # Create a photo WITH thumbnail
        media_with_thumb = PartRequestMedia(
            part_request=part_request,
            media_type=PartRequestMedia.MediaType.PHOTO,
            display_order=0,
        )
        media_with_thumb.file.save("with_thumb.jpg", ContentFile(b"fake"), save=False)
        media_with_thumb.thumbnail_file.save("thumb.jpg", ContentFile(b"fake"), save=True)

        # Create a photo with NULL thumbnail
        media_null_thumb = PartRequestMedia(
            part_request=part_request,
            media_type=PartRequestMedia.MediaType.PHOTO,
            display_order=1,
            thumbnail_file=None,
        )
        media_null_thumb.file.save("null_thumb.jpg", ContentFile(b"fake"), save=True)

        message = format_discord_message("part_request_created", part_request)

        # Should only have 1 embed (the photo with thumbnail)
        self.assertEqual(len(message["embeds"]), 1)
        self.assertIn("image", message["embeds"][0])

    def test_format_part_request_update_with_photos(self):
        """Format a part request update with photos creates multiple embeds for gallery."""
        from flipfix.apps.parts.models import PartRequestUpdateMedia

        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
        )

        # Create mock photos with thumbnails (Discord uses thumbnails, not originals)
        for i in range(3):
            media = PartRequestUpdateMedia(
                update=update,
                media_type=PartRequestUpdateMedia.MediaType.PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=False)
            media.thumbnail_file.save(
                f"test{i}_thumb.jpg", ContentFile(b"fake thumbnail"), save=True
            )

        message = format_discord_message("part_request_update_created", update)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # Image URLs should use thumbnail_file, not file
        self.assertIn("_thumb", message["embeds"][0]["image"]["url"])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_part_request_update_excludes_photos_without_thumbnails(self):
        """Photos without thumbnails are excluded from Discord gallery."""
        from flipfix.apps.parts.models import PartRequestUpdateMedia

        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered from Marco Specialties",
        )

        # Create a photo WITH thumbnail
        media_with_thumb = PartRequestUpdateMedia(
            update=update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            display_order=0,
        )
        media_with_thumb.file.save("with_thumb.jpg", ContentFile(b"fake"), save=False)
        media_with_thumb.thumbnail_file.save("thumb.jpg", ContentFile(b"fake"), save=True)

        # Create a photo with NULL thumbnail
        media_null_thumb = PartRequestUpdateMedia(
            update=update,
            media_type=PartRequestUpdateMedia.MediaType.PHOTO,
            display_order=1,
            thumbnail_file=None,
        )
        media_null_thumb.file.save("null_thumb.jpg", ContentFile(b"fake"), save=True)

        message = format_discord_message("part_request_update_created", update)

        # Should only have 1 embed (the photo with thumbnail)
        self.assertEqual(len(message["embeds"]), 1)
        self.assertIn("image", message["embeds"][0])

    @override_settings(SITE_URL="https://example.com")
    def test_format_part_request_renders_record_links(self):
        """Part request text with [[type:ref]] links renders as Discord links."""
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        part_request = create_part_request(
            text=f"Need parts for [[machine:id:{ref_machine.pk}]] left flipper",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        message = format_discord_message("part_request_created", part_request)

        description = message["embeds"][0]["description"]

        # Link should be rendered with absolute URL
        self.assertIn("Attack From Mars", description)
        self.assertIn("https://example.com/machines/attack-from-mars/", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)

    @override_settings(SITE_URL="https://example.com")
    def test_format_part_request_update_renders_record_links(self):
        """Part request update text with [[type:ref]] links renders as Discord links."""
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        part_request = create_part_request(
            text="Need parts",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text=f"Ordered parts for [[machine:id:{ref_machine.pk}]]",
        )
        message = format_discord_message("part_request_update_created", update)

        description = message["embeds"][0]["description"]

        # Link should be rendered with absolute URL
        self.assertIn("Attack From Mars", description)
        self.assertIn("https://example.com/machines/attack-from-mars/", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)

    @override_settings(SITE_URL="https://example.com")
    def test_format_part_request_update_renders_links_in_linked_record_preview(self):
        """Parent PR text preview renders [[type:ref]] as plain text labels."""
        ref_machine = create_machine(name="Attack From Mars", slug="attack-from-mars")
        part_request = create_part_request(
            text=f"Need parts for [[machine:id:{ref_machine.pk}]]",
            requested_by=self.maintainer,
            machine=self.machine,
        )
        update = create_part_request_update(
            part_request=part_request,
            posted_by=self.maintainer,
            text="Ordered from supplier",
        )
        message = format_discord_message("part_request_update_created", update)

        description = message["embeds"][0]["description"]

        # Parent PR preview should contain the machine name as plain text
        self.assertIn("Attack From Mars", description)
        # Raw storage format should NOT appear
        self.assertNotIn("[[machine:id:", description)


@tag("tasks")
class GetBaseUrlTests(TestCase):
    """Tests for the get_base_url helper function."""

    def test_strips_trailing_slash(self):
        """Trailing slash is stripped to prevent double slashes in URLs."""
        with self.settings(SITE_URL="https://example.com/"):
            self.assertEqual(get_base_url(), "https://example.com")

    def test_no_trailing_slash_unchanged(self):
        """URL without trailing slash is returned as-is."""
        with self.settings(SITE_URL="https://example.com"):
            self.assertEqual(get_base_url(), "https://example.com")

    def test_raises_when_not_configured(self):
        """Raises ValueError when SITE_URL is not set."""
        with self.settings(SITE_URL=""):
            with self.assertRaises(ValueError):
                get_base_url()
