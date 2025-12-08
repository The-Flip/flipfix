"""Remove WebhookEndpoint and WebhookEventSubscription models.

Webhook URL is now stored in Constance settings as DISCORD_WEBHOOK_URL.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("discord", "0003_add_discord_message_mapping"),
    ]

    operations = [
        migrations.DeleteModel(
            name="WebhookEventSubscription",
        ),
        migrations.DeleteModel(
            name="WebhookEndpoint",
        ),
    ]
