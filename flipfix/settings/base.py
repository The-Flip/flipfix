"""Base Django settings."""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from decouple import Csv, config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_DIR = REPO_ROOT

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Base absolute URL for external systems following links into this system,
# such as Discord webhooks and Discord bot record links.
# Must be publicly accessible - localhost won't work for Discord integration
SITE_URL = config("SITE_URL", default="")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_q",
    "constance",
    "constance.backends.database",
    "simple_history",
    "oauth2_provider",
    "flipfix.apps.core",
    "flipfix.apps.accounts",
    "flipfix.apps.catalog",
    "flipfix.apps.maintenance",
    "flipfix.apps.parts",
    "flipfix.apps.discord",
    "flipfix.apps.wiki",
    "flipfix.apps.oauth",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "flipfix.middleware.MaintainerAccessMiddleware",
    "flipfix.middleware.RequestContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "flipfix.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [REPO_ROOT / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "constance.context_processors.config",
            ],
        },
    },
]

WSGI_APPLICATION = "flipfix.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": REPO_ROOT / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# django-q2 configuration (DB-backed queue)
Q_CLUSTER = {
    "name": "flipfix_worker",
    "orm": "default",
    "workers": 1,
    "timeout": 600,
    "retry": 660,
    "save_limit": 50,
    "queue_limit": 50,
    "recycle": 5,
    "bulk": 1,
    "catch_up": False,
    "max_attempts": 1,
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = REPO_ROOT / "static_collected"
STATICFILES_DIRS = [REPO_ROOT / "flipfix/static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = REPO_ROOT / "media"

# Whitenoise serves files from this directory at the site root (e.g. robots.txt)
WHITENOISE_ROOT = REPO_ROOT / "public"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Pagination size, used by infinite scrolling
LIST_PAGE_SIZE = 10

# Rate limiting for public problem reports
RATE_LIMIT_REPORTS_PER_IP = config("RATE_LIMIT_REPORTS_PER_IP", default=5, cast=int)
RATE_LIMIT_WINDOW_MINUTES = config("RATE_LIMIT_WINDOW_MINUTES", default=10, cast=int)

# Transcoding upload authentication token (shared between web and worker services)
TRANSCODING_UPLOAD_TOKEN = config("TRANSCODING_UPLOAD_TOKEN", default=None)

# Logging levels (env-overridable)
# Log level of this application's code: flipfix.* loggers
APP_LOG_LEVEL = config("APP_LOG_LEVEL", default="INFO").upper()
# Log level of the Discord bot
DISCORD_BOT_LOG_LEVEL = config("DISCORD_BOT_LOG_LEVEL", default=None)
# Log level of Django framework internals: django.* and django_q loggers
DJANGO_LOG_LEVEL = config("DJANGO_LOG_LEVEL", default="WARNING").upper()
# Root logger (third-party libraries, unconfigured loggers)
LOG_LEVEL = config("LOG_LEVEL", default="WARNING").upper()

# django-constance configuration (admin-editable settings)
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"

CONSTANCE_CONFIG = {
    # Public access
    "PUBLIC_ACCESS_ENABLED": (False, "Allow unauthenticated visitors to browse public pages", bool),
    # Discord Bot settings (inbound - listening to Discord messages)
    "DISCORD_BOT_ENABLED": (False, "Master switch for Discord bot", bool),
    "DISCORD_BOT_TOKEN": ("", "Discord bot token (keep secret!)", str),
    "DISCORD_GUILD_ID": ("", "Discord server (guild) ID", str),
    # LLM settings
    "ANTHROPIC_API_KEY": ("", "Anthropic API key for Claude (keep secret!)", str),
    # Discord Webhook settings (outbound - posting to Discord)
    "DISCORD_WEBHOOK_URL": ("", "Discord webhook URL to post notifications to", str),
    "DISCORD_WEBHOOKS_ENABLED": (
        False,
        "Master switch for all Discord webhook notifications",
        bool,
    ),
}

CONSTANCE_CONFIG_FIELDSETS = (
    (
        "Public Access",
        ("PUBLIC_ACCESS_ENABLED",),
    ),
    (
        "Discord Webhooks (Outbound)",
        (
            "DISCORD_WEBHOOK_URL",
            "DISCORD_WEBHOOKS_ENABLED",
        ),
    ),
    (
        "Discord Bot (Inbound)",
        (
            "DISCORD_BOT_ENABLED",
            "DISCORD_BOT_TOKEN",
            "DISCORD_GUILD_ID",
            "ANTHROPIC_API_KEY",
        ),
    ),
)

# Logging configuration - conservative defaults for production
# Override in dev.py for more verbose output
LOGGING: MutableMapping[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "flipfix.logging.RequestContextFilter",
        },
    },
    "formatters": {
        "dev": {
            "()": "flipfix.logging.DevFormatter",
        },
        "json": {
            "()": "flipfix.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "flipfix": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "flipfix.apps.discord": {
            "handlers": ["console"],
            "level": (DISCORD_BOT_LOG_LEVEL or APP_LOG_LEVEL),
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "django_q": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
    },
}

# OAuth2/OIDC Provider (django-oauth-toolkit)
# Required by DOT's swappable model machinery for migration dependency resolution
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"
_oidc_rsa_key = config("OIDC_RSA_PRIVATE_KEY", default="")
_oidc_issuer = SITE_URL or ""
OAUTH2_PROVIDER = {
    "OIDC_ENABLED": True,
    "OIDC_ISS_ENDPOINT": _oidc_issuer,
    "OIDC_RSA_PRIVATE_KEY": _oidc_rsa_key,
    "SCOPES": {
        "openid": "OpenID Connect",
        "profile": "User profile",
        "email": "Email address",
        "capabilities": "App-specific capabilities",
    },
    "OAUTH2_VALIDATOR_CLASS": "flipfix.apps.oauth.validators.FlipFixOAuth2Validator",
    "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
    "REFRESH_TOKEN_EXPIRE_SECONDS": 2592000,  # 30 days
    "ROTATE_REFRESH_TOKEN": True,
    "PKCE_REQUIRED": True,
    "ALLOWED_REDIRECT_URI_SCHEMES": ["https"],
}
