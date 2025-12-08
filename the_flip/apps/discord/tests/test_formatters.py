"""Tests for Discord message formatting."""

from django.core.files.base import ContentFile
from django.test import TestCase

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import (
    create_log_entry,
    create_machine,
    create_part_request,
    create_part_request_update,
    create_problem_report,
    create_staff_user,
)
from the_flip.apps.discord.formatters import format_discord_message, format_test_message
from the_flip.apps.discord.models import DiscordUserLink
from the_flip.apps.maintenance.models import LogEntryMedia
from the_flip.apps.parts.models import PartRequest


class DiscordFormatterTests(TestCase):
    """Tests for Discord message formatting.

    These tests verify the structure of webhook messages, not exact wording.
    This makes them resilient to copy changes.
    """

    def setUp(self):
        self.machine = create_machine()
        self.staff_user = create_staff_user()

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
        self.assertIn(self.machine.display_name, embed["title"])

        # URL points to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["url"])

    def test_format_log_entry_created(self):
        """Format a new log entry message."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.staff_user)
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Required fields exist
        self.assertIn("title", embed)
        self.assertIn("description", embed)
        self.assertIn("url", embed)
        self.assertIn("color", embed)

        # Title includes machine name
        self.assertIn(self.machine.display_name, embed["title"])

        # Description includes log text
        self.assertIn(log_entry.text, embed["description"])

        # URL points to the log entry
        self.assertIn(f"/logs/{log_entry.pk}/", embed["url"])

    def test_format_log_entry_with_problem_report(self):
        """Format a log entry attached to a problem report includes PR link."""
        report = create_problem_report(machine=self.machine)
        log_entry = create_log_entry(
            machine=self.machine,
            created_by=self.staff_user,
            problem_report=report,
        )
        message = format_discord_message("log_entry_created", log_entry)

        embed = message["embeds"][0]

        # Description includes link to the problem report
        self.assertIn(f"/problem-reports/{report.pk}/", embed["description"])

    def test_format_log_entry_with_photos(self):
        """Format a log entry with photos creates multiple embeds for gallery."""
        log_entry = create_log_entry(machine=self.machine, created_by=self.staff_user)

        # Create mock photos
        for i in range(3):
            media = LogEntryMedia(
                log_entry=log_entry,
                media_type=LogEntryMedia.TYPE_PHOTO,
                display_order=i,
            )
            media.file.save(f"test{i}.jpg", ContentFile(b"fake image data"), save=True)

        message = format_discord_message("log_entry_created", log_entry)

        # Should have 3 embeds (main + 2 additional for gallery effect)
        self.assertEqual(len(message["embeds"]), 3)

        # First embed has title, description, and image
        self.assertIn("title", message["embeds"][0])
        self.assertIn("image", message["embeds"][0])

        # All embeds share the same URL (required for Discord gallery)
        main_url = message["embeds"][0]["url"]
        for embed in message["embeds"][1:]:
            self.assertIn("image", embed)
            self.assertEqual(embed["url"], main_url)

    def test_format_log_entry_uses_discord_name_when_linked(self):
        """Log entry uses Discord display name when maintainer is linked."""
        maintainer = Maintainer.objects.get(user=self.staff_user)

        # Create Discord link
        DiscordUserLink.objects.create(
            discord_user_id="123456789",
            discord_username="discorduser",
            discord_display_name="Discord Display Name",
            maintainer=maintainer,
        )

        log_entry = create_log_entry(machine=self.machine, created_by=self.staff_user)
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


class PartRequestWebhookFormatterTests(TestCase):
    """Tests for part request Discord webhook formatting."""

    def setUp(self):
        self.staff_user = create_staff_user(username="teststaff")
        self.maintainer = Maintainer.objects.get(user=self.staff_user)
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

        # Title includes part request ID
        self.assertIn(f"#{part_request.pk}", embed["title"])

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
            status=PartRequest.STATUS_ORDERED,
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
