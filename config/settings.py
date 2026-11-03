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
    "core",                         # public landing page
    "accounts",                     # businesses, users, roles, sign-in
    "timetrack",                    # projects, tasks, time entries, timesheets, rates
    "reports",                      # reports and CSV export (no tables of its own)
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
                "timetrack.context_processors.approvals",  # approvals badge in the menu
                "core.context_processors.company",  # company details for the footer
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database -------------------------------------------------------------
# Phase 1 uses SQLite: a single file (db.sqlite3), no server to install.
# We will switch to PostgreSQL in a later phase by changing only this block.
# ATOMIC_REQUESTS wraps each request in a transaction: if anything fails,
# nothing half-saved is left behind.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "ATOMIC_REQUESTS": True,
    }
}


# --- Users and sign-in ---------------------------------------------------

# Use our own User model (accounts/models.py) instead of Django's default.
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"                          # where @login_required sends people
LOGIN_REDIRECT_URL = "timetrack:dashboard"   # after signing in
LOGOUT_REDIRECT_URL = "core:home"            # after signing out

# Sign users out when they close the browser, and after 8 hours regardless.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 8 * 60 * 60


# --- Company details (shown in the footer of every page) -------------------

COMPANY = {
    "name": "Vora Global Solutions",
    "address": "Flat 1 Vienna Court, Vesey Close, Farnborough, England, GU14 8UT",
    "email": "info@voraglobalsolutions.com",
    "phone": "+44 7404 741045",
    # Paste the full page addresses here (https://...). Empty = icon hidden.
    "linkedin_url": "",
    "facebook_url": "",
}


# --- Billing ----------------------------------------------------------------

# Currency for all billing rates and amounts.
BILLING_CURRENCY = "GBP"
BILLING_CURRENCY_SYMBOL = "£"


# --- Passwords ------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
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
