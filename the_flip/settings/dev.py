"""Development settings."""

from __future__ import annotations

from copy import deepcopy

from .base import *  # noqa
from .base import LOGGING as BASE_LOGGING

LOGGING = deepcopy(BASE_LOGGING)

DEBUG = True

# Whitenoise for serving the app's static files (CSS, JS, etc)
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Development logging - more verbose, human-readable format with extras
LOGGING["handlers"]["console"]["formatter"] = "dev"  # noqa: F405
LOGGING["loggers"]["the_flip"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.request"]["level"] = "INFO"  # noqa: F405
LOGGING["loggers"]["django.server"]["level"] = "INFO"  # noqa: F405
