import os

import dj_database_url

# Set SECRET_KEY before importing base settings (which requires it)
# Not a real secret - tests don't need cryptographic security
os.environ.setdefault("SECRET_KEY", "test-key-not-secret")  # pragma: allowlist secret

from .base import *  # noqa

DEBUG = False
SITE_URL = "http://testserver"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use DATABASE_URL if provided (CI uses Postgres), otherwise SQLite for local dev
DATABASES["default"] = dj_database_url.config(  # type: ignore[assignment]
    default="sqlite://:memory:",
    conn_max_age=600,
)

# Suppress noisy Django-Q logging during tests
Q_CLUSTER["log_level"] = "WARNING"  # type: ignore[name-defined]  # noqa: F405

# Suppress app logs during tests
# Tests verify behavior through assertions, not log inspection
LOGGING["loggers"]["the_flip"]["level"] = "CRITICAL"  # type: ignore[index]  # noqa: F405
LOGGING["loggers"]["the_flip.apps.discord"]["level"] = "CRITICAL"  # type: ignore[index]  # noqa: F405
