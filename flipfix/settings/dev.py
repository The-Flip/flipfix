"""Development settings."""

from __future__ import annotations

from copy import deepcopy

import dj_database_url
from decouple import config

from .base import *  # noqa
from .base import LOGGING as BASE_LOGGING

LOGGING = deepcopy(BASE_LOGGING)

DEBUG = True

# Database: SQLite by default (zero-config), or Postgres when DATABASE_URL is set.
# Read via python-decouple (environment, then .env) for consistency with the rest
# of the settings — dj_database_url's own reader only checks os.environ, which the
# project never populates from .env. Point DATABASE_URL at the local Postgres from
# docker-compose.yml (see .env.example) to match production's engine and to
# receive `make sync-prod` data.
DATABASES["default"] = dj_database_url.parse(  # type: ignore[assignment]  # noqa: F405
    config("DATABASE_URL", default=f"sqlite:///{REPO_ROOT / 'db.sqlite3'}"),  # noqa: F405
    conn_max_age=600,
)

# Whitenoise for serving the app's static files (CSS, JS, etc)
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Development logging - more verbose, human-readable format with extras
LOGGING["handlers"]["console"]["formatter"] = "dev"  # noqa: F405
LOGGING["loggers"]["flipfix"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.request"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.server"]["level"] = "INFO"  # noqa: F405

# Allow HTTP redirect URIs for local OAuth2 development
OAUTH2_PROVIDER["ALLOWED_REDIRECT_URI_SCHEMES"] = ["http", "https"]  # noqa: F405
