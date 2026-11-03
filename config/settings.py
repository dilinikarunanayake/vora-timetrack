"""
Django settings for the Vora TimeTrack project.

Settings control how the whole project behaves: which apps are installed,
which database is used, where templates and static files live, and so on.

Secrets (like SECRET_KEY) are NOT written in this file. They are read from
environment variables, which we load from a local `.env` file during
development. The `.env` file is listed in `.gitignore`, so it never ends
up in Git.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# BASE_DIR is the project root folder (the one containing manage.py).
BASE_DIR = Path(__file__).resolve().parent.parent

# Read KEY=value pairs from .env into environment variables (if the file exists).
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    """Read an environment variable as True/False."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Security -------------------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY is not set. Copy .env.example to .env and add a key "
        "(see 'Run it locally' in README.md)."
    )

# DEBUG shows detailed error pages. Useful locally, dangerous in production.
DEBUG = env_bool("DJANGO_DEBUG", default=False)

# Which host names this site may be served under, e.g. "localhost,127.0.0.1".
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]


# --- Applications ---------------------------------------------------------

INSTALLED_APPS = [
    # Built-in Django apps
    "django.contrib.admin",         # admin site at /admin/
    "django.contrib.auth",          # users, groups, permissions, login
    "django.contrib.contenttypes",
    "django.contrib.sessions",      # remembers logged-in users between requests
    "django.contrib.messages",      # one-off notifications ("Timesheet submitted")
    "django.contrib.staticfiles",   # serves CSS/JS/images
    # Our apps
    "core",                         # landing page and dashboard
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Project-wide templates folder (base.html lives here).
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database -------------------------------------------------------------
# Phase 1 uses SQLite: a single file (db.sqlite3), no server to install.
# We will switch to PostgreSQL in a later phase by changing only this block.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# --- Passwords ------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Language and time ----------------------------------------------------

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True  # store times in UTC, display in TIME_ZONE


# --- Static files (CSS, JavaScript, images) -------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
