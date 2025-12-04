"""Web service production settings."""

from .prod_base import *  # noqa

# Whitenoise for static/media file serving
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]  # noqa: F405
MIDDLEWARE.insert(1, "the_flip.middleware.MediaWhiteNoiseMiddleware")  # noqa: F405
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
