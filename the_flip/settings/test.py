import dj_database_url

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
