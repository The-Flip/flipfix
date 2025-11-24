"""Base Django settings."""

from __future__ import annotations

from pathlib import Path

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
    "whitenoise.runserver_nostatic",
    "django_q",
    "the_flip.apps.core",
    "the_flip.apps.accounts",
    "the_flip.apps.catalog",
    "the_flip.apps.maintenance",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "the_flip.middleware.MediaWhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

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
