"""
Production settings for djangoWocshack_5.

Inherits base.py and enforces strict security settings.

Usage:
    DJANGO_SETTINGS_MODULE=djangoWocshack_5.settings.production

Optional environment variables:
    SECRET_KEY      – A long random string. If unset, a fresh random key is
                      generated on each process start (sessions/CSRF tokens
                      from earlier runs become invalid on restart).
    ALLOWED_HOSTS   – Currently hardcoded to ['*'] below; env value ignored.
"""

from decouple import config, Csv
from django.core.management.utils import get_random_secret_key

from .base import *  # noqa: F401,F403

# ── Debug ───────────────────────────────────────────────────────────────────
# Always off in production, regardless of .env value.

DEBUG = False

# ── Secrets (no insecure defaults in production) ────────────────────────────

SECRET_KEY = config('SECRET_KEY', default=get_random_secret_key())
ALLOWED_HOSTS = ['*']

# Permissive CSRF trusted origins — accept any HTTPS/HTTP host. Suitable for
# the public CTF deployment where the tunnel hostname rotates and the proxy
# may not forward Host/X-Forwarded-Host reliably.
CSRF_TRUSTED_ORIGINS = ['https://*', 'http://*']

# ── HTTPS / Security hardening ──────────────────────────────────────────────
# TLS is terminated by the reverse proxy in front of Django, so Django itself
# speaks HTTP and must not enforce HTTPS-only headers (they would double-redirect
# or break the proxy chain). SECURE_PROXY_SSL_HEADER + USE_X_FORWARDED_HOST are
# still set in base.py so request.is_secure() reflects the public scheme.
