"""Tests for Discord message formatting."""

from django.core.files.base import ContentFile
from django.test import TestCase

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    TemporaryMediaMixin,
    create_log_entry,
    create_machine,
    create_maintainer_user,
    create_part_request,
    create_part_request_update,
    create_problem_report,
)
from the_flip.apps.discord.formatters import (
    format_discord_message,
    format_test_message,
    get_base_url,
)
from the_flip.apps.discord.models import DiscordUserLink
from the_flip.apps.maintenance.models import LogEntryMedia
from the_flip.apps.parts.models import PartRequest


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
        from the_flip.apps.maintenance.models import ProblemReportMedia

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

    def test_format_test_message(self):
        """Format a test message has required structure."""
        message = format_test_message("problem_report_created")

        self.assertIn("embeds", message)
        embed = message["embeds"][0]
        self.assertIn("title", embed)
        self.assertIn("description", embed)


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

        # Title includes ID and machine name
        self.assertIn(f"#{part_request.pk}", embed["title"])
        self.assertIn(self.machine.name, embed["title"])

        # Description includes the text
        self.assertIn("flipper rubbers", embed["description"])

        # URL points to the part request
        self.assertIn(f"/parts/{part_request.pk}/", embed["url"])

    def test_format_part_request_status_changed(self):
        """Format a status change message."""
        part_request = create_part_request(
            text="Need new flipper rubbers",
            requested_by=self.maintainer,
            machine=self.machine,
            status=PartRequest.Status.ORDERED,
        )
        message = format_discord_message("part_request_status_changed", part_request)

        embed = message["embeds"][0]

        # Title includes status
        self.assertIn("Ordered", embed["title"])

        # Description includes status
        self.assertIn("Status", embed["description"])

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

        # Title references the part request
        self.assertIn(f"#{part_request.pk}", embed["title"])

        # Description includes the update text
        self.assertIn("Marco Specialties", embed["description"])

    def test_format_part_request_with_photos(self):
        """Format a part request with photos creates multiple embeds for gallery."""
        from the_flip.apps.parts.models import PartRequestMedia

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

    def test_format_part_request_update_with_photos(self):
        """Format a part request update with photos creates multiple embeds for gallery."""
        from the_flip.apps.parts.models import PartRequestUpdateMedia

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
