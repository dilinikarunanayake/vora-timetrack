"""
Django settings for the Vora TimeTrack project.

Settings control how the whole project behaves: which apps are installed,
which database is used, where templates and static files live, and so on.

Secrets (like SECRET_KEY) are NOT written in this file. They are read from
environment variables, which we load from a local `.env` file during
development. The `.env` file is listed in `.gitignore`, so it never ends
up in Git. On the live server, the hosting company sets the same variables.

The same file runs locally AND in production. The switch is DJANGO_DEBUG:
    DJANGO_DEBUG=True   -> your Mac: SQLite, detailed error pages
    DJANGO_DEBUG=False  -> live site: PostgreSQL (DATABASE_URL), HTTPS-only,
                           secure cookies, compressed static files
"""

import os
from pathlib import Path

import dj_database_url
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

# Render tells the app its own web address; allow it automatically.
if os.getenv("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])

# Forms posted from these https:// addresses are trusted (needed behind HTTPS).
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]


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
    # Third-party
    "axes",                         # blocks repeated wrong-password attempts
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serves CSS/images efficiently in production
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",  # must be last
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
# DATABASE_URL picks the database, e.g. postgres://user:password@host:5432/name
# The hosting company provides it. If it's not set (your Mac), SQLite is used.
# ATOMIC_REQUESTS wraps each request in a transaction: if anything fails,
# nothing half-saved is left behind.

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,          # reuse connections for 10 minutes (faster)
        conn_health_checks=True,   # ...but check they're still alive first
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True


# --- Users and sign-in ---------------------------------------------------

# Use our own User model (accounts/models.py) instead of Django's default.
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "login"                          # where @login_required sends people
LOGIN_REDIRECT_URL = "timetrack:dashboard"   # after signing in
LOGOUT_REDIRECT_URL = "core:home"            # after signing out

# Sign users out when they close the browser, and after 8 hours regardless.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 8 * 60 * 60

# django-axes checks sign-in attempts before Django's normal password check.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
# After 5 wrong passwords for the same username, block that username for
# 1 hour, whatever address the attempts come from. (Locking by IP address is
# unreliable behind a hosting company's proxy, and easy to fake.)
# A director can unlock someone early in /admin/ -> Axes -> Access attempts.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCKOUT_PARAMETERS = ["username"]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/locked_out.html"
# axes warns when 'ip_address' isn't a lockout parameter. We lock by username on
# purpose (see above); strong-password rules below cover guessing across accounts.
SILENCED_SYSTEM_CHECKS = ["axes.W006"]


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
# `collectstatic` copies every static file here for the live server.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # In production, file names get a fingerprint (styles.3f2a9c.css) so browsers
    # can cache them for a year yet always fetch new versions after a deploy.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Production security (applies only when DJANGO_DEBUG=False) ----------------

if not DEBUG:
    # The hosting company handles HTTPS and tells Django the original scheme.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True             # http:// -> https://
    SESSION_COOKIE_SECURE = True           # sign-in cookie only sent over HTTPS
    CSRF_COOKIE_SECURE = True
    # HSTS: browsers remember to use HTTPS only. Starts at 1 hour; raise to a
    # year (31536000) once you're happy the site works over HTTPS.
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))
    # Not applied to other voraglobalsolutions.com subdomains: the company
    # website and email may live on other services we don't control.
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    SILENCED_SYSTEM_CHECKS += ["security.W005", "security.W021"]
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    # The health check is called by the hosting company over plain http inside
    # its network, so it must not be redirected.
    SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]


# --- Logging ------------------------------------------------------------------
# Send warnings and errors to the console; the hosting company collects them
# in its "Logs" page.

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "WARNING"), "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
