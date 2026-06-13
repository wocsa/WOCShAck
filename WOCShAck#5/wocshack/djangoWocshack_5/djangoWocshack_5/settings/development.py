"""
Development settings for djangoWocshack_5.

Inherits everything from base.py with relaxed security for local development.

Usage:
    DJANGO_SETTINGS_MODULE=djangoWocshack_5.settings.development
"""

from .base import *  # noqa: F401,F403

# ── Debug ───────────────────────────────────────────────────────────────────

DEBUG = True

# ── Hosts ───────────────────────────────────────────────────────────────────
# Allow all hosts in development for convenience.

ALLOWED_HOSTS = ['*']

# ── CSRF ────────────────────────────────────────────────────────────────────
# Allow all origins for CSRF in development. Django requires scheme-qualified
# entries; "https://*" / "http://*" is the documented wildcard form (Django 4+).

CSRF_TRUSTED_ORIGINS = ['https://*', 'http://*']

# ── Email ───────────────────────────────────────────────────────────────────
# Print emails to console in development.

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
