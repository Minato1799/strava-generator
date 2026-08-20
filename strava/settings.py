"""Django settings for the stateless Vercel deployment."""

import math
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent.parent


def _non_negative_float_env(name, default):
    try:
        value = float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value >= 0 else default


def _non_negative_int_env(name, default):
    try:
        value = int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


IS_VERCEL = os.getenv("VERCEL") == "1"
configured_secret_key = os.getenv("DJANGO_SECRET_KEY", "").strip()
if IS_VERCEL and not configured_secret_key:
    raise RuntimeError("DJANGO_SECRET_KEY must be configured for Vercel deployments")

SECRET_KEY = (
    configured_secret_key
    or "local-development-only-key-with-more-than-fifty-characters-2026"
)
DEBUG = not IS_VERCEL and os.getenv("CONTEXT", "").upper() == "DEBUG"


def _hostname_from_env(name):
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    parsed = urlsplit(raw_value if "://" in raw_value else f"//{raw_value}")
    return parsed.hostname.lower() if parsed.hostname else None


ALLOWED_HOSTS = [] if IS_VERCEL else ["localhost", "127.0.0.1"]
if IS_VERCEL:
    for variable_name in (
        "VERCEL_URL",
        "VERCEL_BRANCH_URL",
        "VERCEL_PROJECT_PRODUCTION_URL",
    ):
        vercel_host = _hostname_from_env(variable_name)
        if vercel_host and vercel_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(vercel_host)

extra_hosts = os.getenv("ALLOWED_HOSTS", "")
if extra_hosts:
    for extra_host in (host.strip() for host in extra_hosts.split(",")):
        if extra_host and extra_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(extra_host)

INSTALLED_APPS = [
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "strava.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", BASE_DIR / "strava_generator" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "strava.wsgi.application"

# The deployed application is intentionally stateless. Route generation and GPX
# export do not require accounts or a database.
DATABASES = {}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# The largest legitimate request is a 10,000-point GPX generation payload and
# is comfortably below this ceiling. Django rejects larger bodies before JSON
# decoding, and the API converts that failure to a small private 413 response.
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_048_576

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "strava_generator" / "static"]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = IS_VERCEL
SECURE_HSTS_SECONDS = 31_536_000 if IS_VERCEL else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_VERCEL
SECURE_HSTS_PRELOAD = IS_VERCEL
SESSION_COOKIE_SECURE = IS_VERCEL
CSRF_COOKIE_SECURE = IS_VERCEL
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# These caches and throttles are intentionally per process. They reduce duplicate
# public-provider traffic without introducing a database or retaining route data
# beyond the lifetime of a warm application instance.
PROVIDER_CACHE_MAX_ENTRIES = _non_negative_int_env("PROVIDER_CACHE_MAX_ENTRIES", 256)
ROUTE_CACHE_TTL_SECONDS = _non_negative_float_env("ROUTE_CACHE_TTL_SECONDS", 300.0)
SEARCH_CACHE_TTL_SECONDS = _non_negative_float_env("SEARCH_CACHE_TTL_SECONDS", 900.0)
ROUTING_PROVIDER_MIN_INTERVAL_SECONDS = _non_negative_float_env(
    "ROUTING_PROVIDER_MIN_INTERVAL_SECONDS",
    1.05,
)
GEOCODING_PROVIDER_MIN_INTERVAL_SECONDS = _non_negative_float_env(
    "GEOCODING_PROVIDER_MIN_INTERVAL_SECONDS",
    1.05,
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[%(levelname)s] %(asctime)s - %(message)s"},
    },
    "handlers": {
        "stream": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {"level": "INFO", "handlers": ["stream"], "propagate": False},
        "strava_generator": {"level": "INFO", "handlers": ["stream"], "propagate": False},
    },
}
