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

# Use Postgres database from DATABASE_URL environment variable
# Railway automatically provides this when you add a Postgres database
#
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
    sys.exit(1)

if not active_db_url.startswith("postgres"):
    sys.exit(1)


DATABASES = {
    "default": dj_database_url.parse(
        active_db_url,
        conn_max_age=600,
        conn_health_checks=True,
    )
}
