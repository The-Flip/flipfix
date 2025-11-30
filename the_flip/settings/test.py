import dj_database_url

from .base import *  # noqa

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Use DATABASE_URL if provided (CI uses Postgres), otherwise SQLite for local dev
DATABASES["default"] = dj_database_url.config(  # type: ignore[assignment]
    default="sqlite://:memory:",
    conn_max_age=600,
)
