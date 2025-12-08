"""Base Django settings."""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from decouple import Csv, config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASE_DIR = REPO_ROOT

SECRET_KEY = config("SECRET_KEY", default="dev-secret-key")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

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
    "the_flip.apps.core",
    "the_flip.apps.accounts",
    "the_flip.apps.catalog",
    "the_flip.apps.maintenance",
    "the_flip.apps.parts",
    "the_flip.apps.discord",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "the_flip.middleware.RequestContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "the_flip.urls"

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

WSGI_APPLICATION = "the_flip.wsgi.application"

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
    "name": "the_flip_worker",
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
STATICFILES_DIRS = [REPO_ROOT / "the_flip/static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = REPO_ROOT / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Rate limiting for public problem reports
RATE_LIMIT_REPORTS_PER_IP = config("RATE_LIMIT_REPORTS_PER_IP", default=5, cast=int)
RATE_LIMIT_WINDOW_MINUTES = config("RATE_LIMIT_WINDOW_MINUTES", default=10, cast=int)

# Transcoding upload authentication token (shared between web and worker services)
TRANSCODING_UPLOAD_TOKEN = config("TRANSCODING_UPLOAD_TOKEN", default=None)

# Logging levels (env-overridable)
LOG_LEVEL = config("LOG_LEVEL", default="WARNING").upper()
APP_LOG_LEVEL = config("APP_LOG_LEVEL", default="INFO").upper()
DJANGO_LOG_LEVEL = config("DJANGO_LOG_LEVEL", default="WARNING").upper()
DISCORD_BOT_LOG_LEVEL = config("DISCORD_BOT_LOG_LEVEL", default=None)

# django-constance configuration (admin-editable settings)
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"

CONSTANCE_CONFIG = {
    "PARTS_ENABLED": (False, "Enable the parts request feature", bool),
    # Discord Bot settings (inbound - listening to Discord messages)
    "DISCORD_BOT_ENABLED": (False, "Master switch for Discord bot", bool),
    "DISCORD_BOT_TOKEN": ("", "Discord bot token (keep secret!)", str),
    "DISCORD_GUILD_ID": ("", "Discord server (guild) ID", str),
    # LLM settings
    "ANTHROPIC_API_KEY": ("", "Anthropic API key for Claude (keep secret!)", str),
    # Discord Webhook settings (outbound - posting to Discord)
    "DISCORD_WEBHOOK_URL": ("", "Discord webhook URL to post notifications to", str),
    "DISCORD_WEBHOOKS_ENABLED": (True, "Master switch for all Discord webhook notifications", bool),
    "DISCORD_WEBHOOKS_PROBLEM_REPORTS": (True, "Send webhooks for problem report events", bool),
    "DISCORD_WEBHOOKS_LOG_ENTRIES": (True, "Send webhooks for log entry events", bool),
    "DISCORD_WEBHOOKS_PARTS": (True, "Send webhooks for part request events", bool),
}

CONSTANCE_CONFIG_FIELDSETS = (
    ("Feature Flags", ("PARTS_ENABLED",)),
    (
        "Discord Webhooks (Outbound)",
        (
            "DISCORD_WEBHOOK_URL",
            "DISCORD_WEBHOOKS_ENABLED",
            "DISCORD_WEBHOOKS_PROBLEM_REPORTS",
            "DISCORD_WEBHOOKS_LOG_ENTRIES",
            "DISCORD_WEBHOOKS_PARTS",
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

# Valid domains for Discord bot URL parsing (to identify links to this app)
# Production domain is derived from SITE_URL; localhost entries are for dev/test
DISCORD_VALID_DOMAINS = config("DISCORD_VALID_DOMAINS", default="localhost,127.0.0.1", cast=Csv())

# Logging configuration - conservative defaults for production
# Override in dev.py for more verbose output
LOGGING: MutableMapping[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {
            "()": "the_flip.logging.RequestContextFilter",
        },
    },
    "formatters": {
        "dev": {
            "()": "the_flip.logging.DevFormatter",
        },
        "json": {
            "()": "the_flip.logging.JsonFormatter",
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
        "the_flip": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "the_flip.apps.discord": {
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
