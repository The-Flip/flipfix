"""Admin interface for webhook configuration."""

import json

from django.contrib import admin, messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse

from .formatters import format_test_message
from .models import WebhookEndpoint, WebhookEventSubscription, WebhookSettings
from .tasks import send_test_webhook


class WebhookEventSubscriptionInline(admin.TabularInline):
    model = WebhookEventSubscription
    extra = 1
    fields = ("event_type", "is_enabled")


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled", "subscribed_events", "created_at")
    list_filter = ("is_enabled",)
    search_fields = ("name", "url")
    readonly_fields = ("created_at", "updated_at")
    inlines = (WebhookEventSubscriptionInline,)
    fieldsets = (
        (None, {"fields": ("name", "url", "is_enabled")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    change_form_template = "admin/webhooks/webhookendpoint/change_form.html"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["event_choices"] = WebhookEndpoint.EVENT_CHOICES
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(description="Subscribed Events")
    def subscribed_events(self, obj):
        events = obj.subscriptions.filter(is_enabled=True).values_list("event_type", flat=True)
        if not events:
            return "-"
        # Get display names
        event_map = dict(WebhookEndpoint.EVENT_CHOICES)
        return ", ".join(event_map.get(e, e) for e in events)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:pk>/test/<str:event_type>/",
                self.admin_site.admin_view(self.test_webhook_view),
                name="webhooks_webhookendpoint_test",
            ),
            path(
                "<int:pk>/preview/<str:event_type>/",
                self.admin_site.admin_view(self.preview_webhook_view),
                name="webhooks_webhookendpoint_preview",
            ),
        ]
        return custom_urls + urls

    def test_webhook_view(self, request, pk, event_type):
        """Send a test webhook to the endpoint."""
        result = send_test_webhook(pk, event_type)
        if result["status"] == "success":
            messages.success(request, result["message"])
        else:
            messages.error(request, f"Test failed: {result.get('error', 'Unknown error')}")

        return HttpResponseRedirect(reverse("admin:webhooks_webhookendpoint_change", args=[pk]))

    def preview_webhook_view(self, request, pk, event_type):
        """Return the test payload JSON for the given endpoint/event."""
        if not WebhookEndpoint.objects.filter(pk=pk).exists():
            return HttpResponse(
                json.dumps({"error": "Endpoint not found"}, indent=2),
                status=404,
                content_type="application/json",
            )

        payload = format_test_message(event_type)
        return HttpResponse(
            json.dumps(payload, indent=2),
            content_type="application/json",
        )


@admin.register(WebhookSettings)
class WebhookSettingsAdmin(admin.ModelAdmin):
    """Admin for the singleton webhook settings."""

    list_display = (
        "webhooks_enabled",
        "problem_reports_enabled",
        "log_entries_enabled",
    )
    fieldsets = (
        (
            "Global Settings",
            {
                "fields": ("webhooks_enabled",),
                "description": "Turn all webhooks on/off for the site. When off, no webhook deliveries or tests are sent.",
            },
        ),
        (
            "Event Type Settings",
            {
                "fields": ("problem_reports_enabled", "log_entries_enabled"),
                "description": "Choose which event categories can send webhooks. These take effect only if the global switch is on.",
            },
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance (singleton)
        return not WebhookSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of the singleton
        return False

    def changelist_view(self, request, extra_context=None):
        # Always redirect to the singleton instance instead of showing a list.
        obj = WebhookSettings.get_settings()
        return HttpResponseRedirect(reverse("admin:webhooks_webhooksettings_change", args=[obj.pk]))
