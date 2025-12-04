"""Worker-specific production settings (no web dependencies like whitenoise)."""

from .prod import *  # noqa

# Remove whitenoise from installed apps
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "whitenoise.runserver_nostatic"]  # noqa: F405

# Remove whitenoise middleware
MIDDLEWARE = [m for m in MIDDLEWARE if "WhiteNoise" not in m]  # noqa: F405

# Use default static files storage (worker doesn't serve static files)
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
