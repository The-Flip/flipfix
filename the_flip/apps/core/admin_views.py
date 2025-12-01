"""Custom admin-only debug dashboard."""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

import django
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseForbidden
from django.shortcuts import render


def _mask(value: str | None) -> str:
    """Return a masked value for secrets."""
    if not value:
        return ""
    if len(value) <= 6:
        return "•••"
    return f"{value[:4]}…{value[-2:]}"


def admin_debug_dashboard(request):
    """Superuser-only dashboard showing selected runtime diagnostics."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("Superuser access required")

    # Whitelisted environment variables (mask sensitive ones)
    env_vars: list[dict[str, Any]] = []
    env_config = {
        "DJANGO_SETTINGS_MODULE": {"secret": False},
        "RAILWAY_ENVIRONMENT_NAME": {"secret": False},
        "RAILWAY_DEPLOYMENT_ID": {"secret": False},
        "DATABASE_URL": {"secret": True},
        "DATABASE_PUBLIC_URL": {"secret": True},
        "SITE_URL": {"secret": False},
        "DJANGO_WEB_SERVICE_URL": {"secret": False},
        "TRANSCODING_UPLOAD_TOKEN": {"secret": True},
        "SECRET_KEY": {"secret": True},
    }
    for key, meta in env_config.items():
        raw_value = os.environ.get(key)
        env_vars.append(
            {
                "key": key,
                "value": _mask(raw_value) if meta["secret"] else raw_value,
                "is_secret": meta["secret"],
                "is_set": bool(raw_value),
            }
        )

    # Settings/DB overview (non-secret)
    db_settings = settings.DATABASES.get("default", {})
    db_display = {
        "ENGINE": db_settings.get("ENGINE", ""),
        "NAME": db_settings.get("NAME", ""),
        "HOST": db_settings.get("HOST", ""),
        "PORT": db_settings.get("PORT", ""),
        "USER": _mask(db_settings.get("USER", "")),
    }

    runtime_info = [
        ("Python", sys.version.split()[0]),
        ("Django", django.get_version()),
        ("DEBUG", str(settings.DEBUG)),
        ("TIME_ZONE", settings.TIME_ZONE),
        ("ALLOWED_HOSTS", ", ".join(settings.ALLOWED_HOSTS)),
        ("STATIC_ROOT", str(getattr(settings, "STATIC_ROOT", ""))),
        ("MEDIA_ROOT", str(getattr(settings, "MEDIA_ROOT", ""))),
        ("Q_CLUSTER name", settings.Q_CLUSTER.get("name", "")),
        ("Platform", platform.platform()),
    ]

    context = {
        "env_vars": env_vars,
        "db_info": db_display,
        "runtime_info": runtime_info,
    }

    response = render(request, "admin/debug_dashboard.html", context)
    response["Cache-Control"] = "no-store"
    return response


# Convenience alias if wiring directly from urls via admin.site.admin_view
admin_debug_view = admin.site.admin_view(admin_debug_dashboard)
