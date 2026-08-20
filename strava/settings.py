"""Django settings for the stateless Vercel deployment."""

import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "local-development-only-key-with-more-than-fifty-characters-2026",
)
DEBUG = os.getenv("CONTEXT", "").upper() == "DEBUG"
IS_VERCEL = bool(os.getenv("VERCEL"))

ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".vercel.app"]
extra_hosts = os.getenv("ALLOWED_HOSTS", "")
if extra_hosts:
    ALLOWED_HOSTS.extend(host.strip() for host in extra_hosts.split(",") if host.strip())

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
