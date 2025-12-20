"""Web service production settings."""

from .prod_base import *  # noqa
from decouple import config  # noqa: F401
from .base import LOGGING, APP_LOG_LEVEL, DJANGO_LOG_LEVEL  # noqa: F401

# Whitenoise for static/media file serving
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
MIDDLEWARE.insert(1, "the_flip.middleware.MediaWhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Web-specific logging levels (overrides APP_LOG_LEVEL/DJANGO_LOG_LEVEL)
LOGGING["loggers"]["the_flip"]["level"] = config(  # type: ignore[name-defined, index]
    "WEB_LOG_LEVEL",
    default=APP_LOG_LEVEL,  # noqa: F405
).upper()
LOGGING["loggers"]["django.request"]["level"] = config(  # type: ignore[name-defined, index]
    "WEB_DJANGO_LOG_LEVEL",
    default=DJANGO_LOG_LEVEL,  # noqa: F405
).upper()
LOGGING["loggers"]["django.server"]["level"] = LOGGING["loggers"]["django.request"]["level"]  # type: ignore[index]
