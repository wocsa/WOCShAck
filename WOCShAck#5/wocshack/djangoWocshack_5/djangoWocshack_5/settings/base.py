"""
Base settings for djangoWocshack_5 project.

Shared configuration that applies to all environments.
Environment-specific overrides live in development.py and production.py.

Secrets and host-specific values are loaded from a .env file via python-decouple.
Copy .env.example to .env and adjust values for your environment.
"""

from pathlib import Path

from decouple import config, Csv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# settings/ is one level deeper than the old settings.py, so we go up three levels.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ── Secrets & core toggles ──────────────────────────────────────────────────

SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-m#+bic7km&a)t))=*ybdfgw5$iy0i)&^acfe=nag*pw@!gouz!',
)

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Behind a TLS-terminating reverse proxy (BunkerWeb): honour X-Forwarded-Proto
# so request.is_secure() returns True and CSRF origin checks see the public
# https scheme, even though gunicorn/runserver only sees plain HTTP upstream.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# Public base URL used in outbound emails (password reset / account activation
# links). Falls back to the request host when empty, but should be set to the
# canonical https URL of the deployment (e.g. "https://example.com") so that
# users on internal hostnames receive a public link.
SITE_URL = config('SITE_URL', default='').rstrip('/')


# ── Application definition ──────────────────────────────────────────────────

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'Todo',
    'Account',
    'Shopping',
    'Bank',
    'Advertisement',
    'Api',
    'Chatbot',
    'Forum',
    'Community',
    'Developer',
    'Moderation',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'djangoWocshack_5.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'shared' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'Advertisement.context_processors.ads',
                'Community.context_processors.unread_messages',
                'Community.context_processors.notification_context',
                'djangoWocshack_5.context_processors.current_app',
            ],
        },
    },
]

WSGI_APPLICATION = 'djangoWocshack_5.wsgi.application'


# ── Database ────────────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# ── Password validation ────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ── Internationalization ───────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# ── Static files ───────────────────────────────────────────────────────────

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'shared' / 'static',
]

# Media files (user-uploaded content, generated GIF previews)
# to prevent direct URL enumeration of static assets
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ── Default PK field type ──────────────────────────────────────────────────

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ── Auth redirects ─────────────────────────────────────────────────────────

LOGIN_REDIRECT_URL = '/account/process'
LOGOUT_REDIRECT_URL = '/'
LOGIN_URL = '/account/login/'


# ── Banking backend ────────────────────────────────────────────────────────

BANKING_HOST = config('BANKING_HOST', default='172.28.0.2')
BANKING_PORT = config('BANKING_PORT', default=7051, cast=int)


# ── Webmail ────────────────────────────────────────────────────────────────

WEBMAIL_HOST = config('WEBMAIL_HOST', default='172.28.0.4')
WEBMAIL_PORT = config('WEBMAIL_PORT', default=8080, cast=int)


# ── Email ──────────────────────────────────────────────────────────────────

EMAIL_BACKEND = config(
    'EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)


# ── Ollama LLM (chatbot RAG pipeline) ─────────────────────────────────────

OLLAMA_BASE_URL = config('OLLAMA_BASE_URL', default='http://ollama:11434')
OLLAMA_MODEL = config('OLLAMA_MODEL', default='gemma3:1b')
