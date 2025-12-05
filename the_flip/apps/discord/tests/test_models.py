"""Tests for Discord models (webhooks and bot configuration)."""

from django.db import IntegrityError
from django.test import TestCase

from the_flip.apps.accounts.models import Maintainer
from the_flip.apps.core.test_utils import create_staff_user
from the_flip.apps.discord.models import (
    DiscordChannel,
    DiscordUserLink,
    WebhookEndpoint,
    WebhookEventSubscription,
)


class WebhookEndpointModelTests(TestCase):
    """Tests for the WebhookEndpoint model."""

    def test_create_endpoint(self):
        """Can create a webhook endpoint."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=True,
        )
        self.assertEqual(str(endpoint), "Test Endpoint (enabled)")

    def test_disabled_endpoint_str(self):
        """Disabled endpoint shows in string representation."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
            is_enabled=False,
        )
        self.assertEqual(str(endpoint), "Test Endpoint (disabled)")


class WebhookEventSubscriptionTests(TestCase):
    """Tests for webhook event subscriptions."""

    def test_create_subscription(self):
        """Can subscribe an endpoint to an event type."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
        )
        subscription = WebhookEventSubscription.objects.create(
            endpoint=endpoint,
            event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
        )
        self.assertEqual(str(subscription), "Test Endpoint → Problem Report Created")

    def test_unique_subscription(self):
        """Cannot create duplicate subscriptions."""
        endpoint = WebhookEndpoint.objects.create(
            name="Test Endpoint",
            url="https://discord.com/api/webhooks/123/abc",
        )
        WebhookEventSubscription.objects.create(
            endpoint=endpoint,
            event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
        )

        with self.assertRaises(IntegrityError):
            WebhookEventSubscription.objects.create(
                endpoint=endpoint,
                event_type=WebhookEndpoint.EVENT_PROBLEM_REPORT_CREATED,
            )


class DiscordChannelModelTests(TestCase):
    """Tests for the DiscordChannel model."""

    def test_create_channel(self):
        """Can create a Discord channel configuration."""
        channel = DiscordChannel.objects.create(
            channel_id="123456789",
            name="maintenance",
            is_enabled=True,
        )
        self.assertEqual(str(channel), "maintenance (enabled)")

    def test_disabled_channel_str(self):
        """Disabled channel shows in string representation."""
        channel = DiscordChannel.objects.create(
            channel_id="123456789",
            name="maintenance",
            is_enabled=False,
        )
        self.assertEqual(str(channel), "maintenance (disabled)")

    def test_unique_channel_id(self):
        """Cannot create duplicate channel IDs."""
        DiscordChannel.objects.create(
            channel_id="123456789",
            name="maintenance",
        )

        with self.assertRaises(IntegrityError):
            DiscordChannel.objects.create(
                channel_id="123456789",
                name="other",
            )


class DiscordUserLinkModelTests(TestCase):
    """Tests for the DiscordUserLink model."""

    def test_create_user_link(self):
        """Can link a Discord user to a maintainer."""
        staff_user = create_staff_user()
        maintainer = Maintainer.objects.get(user=staff_user)

        link = DiscordUserLink.objects.create(
            discord_user_id="987654321",
            discord_username="testuser",
            discord_display_name="Test User",
            maintainer=maintainer,
        )
        self.assertIn("Test User", str(link))
        self.assertIn(str(maintainer), str(link))

    def test_unique_discord_user_id(self):
        """Cannot link same Discord user twice."""
        staff_user = create_staff_user()
        maintainer = Maintainer.objects.get(user=staff_user)

        DiscordUserLink.objects.create(
            discord_user_id="987654321",
            discord_username="testuser",
            maintainer=maintainer,
        )

        # Create another maintainer
        staff_user2 = create_staff_user(username="staff2")
        maintainer2 = Maintainer.objects.get(user=staff_user2)

        with self.assertRaises(IntegrityError):
            DiscordUserLink.objects.create(
                discord_user_id="987654321",  # Same Discord ID
                discord_username="testuser",
                maintainer=maintainer2,
            )
