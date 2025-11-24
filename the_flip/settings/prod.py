from .base import *  # noqa
import dj_database_url
import os
import sys

DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Trust X-Forwarded-Proto header from hosting system's reverse proxy
# This is required when the proxy terminates SSL
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Database Configuration
# ----------------------
# PR environments use SQLite (isolated per PR build)
# Production and staging use PostgreSQL
railway_env = os.environ.get("RAILWAY_ENVIRONMENT_NAME", "")
is_pr_environment = railway_env.startswith("pr-")

if is_pr_environment:
    # PR environment: Use SQLite (isolated database per PR)
    print(f"INFO: Using SQLite for PR environment: {railway_env}", file=sys.stderr)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": REPO_ROOT / "db.sqlite3",  # noqa: F405
        }
    }
else:
    # Production/Staging: Use PostgreSQL
    # Railway's private networking is not available during build phase,
    # so we use DATABASE_PUBLIC_URL during build, then switch to DATABASE_URL
    # (private network) at runtime for better performance.
    database_url = os.environ.get("DATABASE_URL", "")
    database_public_url = os.environ.get("DATABASE_PUBLIC_URL", "")

    # During build, use public URL; at runtime, prefer private URL
    if os.environ.get("RAILWAY_DEPLOYMENT_ID"):
        # Runtime - use private network (DATABASE_URL)
        active_db_url = database_url
        db_type = "private"
    else:
        # Build phase - use public URL
        active_db_url = database_public_url or database_url
        db_type = "public"

    if not active_db_url:
        print(
            f"ERROR: No database URL found. DATABASE_URL={bool(database_url)}, DATABASE_PUBLIC_URL={bool(database_public_url)}, RAILWAY_DEPLOYMENT_ID={bool(os.environ.get('RAILWAY_DEPLOYMENT_ID'))}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not active_db_url.startswith("postgres"):
        print(
            f"ERROR: Database URL must be PostgreSQL. Got: {active_db_url[:20]}...", file=sys.stderr
        )
        sys.exit(1)

    DATABASES = {
        "default": dj_database_url.parse(  # type: ignore[dict-item]
            active_db_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
