import os
import environ
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
LEGACY_UI_DIR = BASE_DIR / 'legacy'

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)

# Read .env file
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')
SECRET_KEY_FALLBACKS = env.list('SECRET_KEY_FALLBACKS', default=[])

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = env('ALLOWED_HOSTS')


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'channels',

    # Internal apps
    'accounts',
    'subscriptions',
    'dashboard',
    'finance',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'accounts.security.SecurityMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'subly.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', LEGACY_UI_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'subly.context_processors.runtime_flags',
            ],
        },
    },
]

WSGI_APPLICATION = 'subly.wsgi.application'
ASGI_APPLICATION = 'subly.asgi.application'


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    'default': env.db() if 'DATABASE_URL' in os.environ else {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
}
database = DATABASES['default']
if database['ENGINE'] == 'django.db.backends.sqlite3':
    if database['NAME'] != ':memory:':
        database['NAME'] = BASE_DIR / database['NAME']
    # Reserve the write lock before transactions read rows they will update.
    database.setdefault('OPTIONS', {}).setdefault('transaction_mode', 'IMMEDIATE')


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTH_USER_MODEL = 'accounts.User'

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = '/static/'
AVATARS_DIR = BASE_DIR / env('AVATARS_DIR', default='avatars')
STATICFILES_DIRS = [LEGACY_UI_DIR / 'static', AVATARS_DIR]
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / env('MEDIA_ROOT', default='media')
PRIVATE_MEDIA_ROOT = BASE_DIR / env('PRIVATE_MEDIA_ROOT', default='private_media')

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_REDIRECT_URL = 'dashboard:home'
LOGOUT_REDIRECT_URL = 'accounts:login'

# Email Configuration
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
EMAIL_PORT = env.int('EMAIL_PORT', default=465 if EMAIL_USE_SSL else 587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=not EMAIL_USE_SSL)
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=15)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@subly.com')
ACCOUNT_PASSWORD_ENCRYPTION_KEY = env('ACCOUNT_PASSWORD_ENCRYPTION_KEY', default='')
ACCOUNT_PASSWORD_LEGACY_FALLBACK = env.bool('ACCOUNT_PASSWORD_LEGACY_FALLBACK', default=True)
PLAID_CLIENT_ID = env('PLAID_CLIENT_ID', default='')
PLAID_SECRET = env('PLAID_SECRET', default='')
PLAID_ENV = env('PLAID_ENV', default='sandbox')
PLAID_COUNTRY_CODES = env.list('PLAID_COUNTRY_CODES', default=['US'])
GMAIL_CLIENT_ID = env('GMAIL_CLIENT_ID', default='')
GMAIL_CLIENT_SECRET = env('GMAIL_CLIENT_SECRET', default='')
GMAIL_REDIRECT_URI = env('GMAIL_REDIRECT_URI', default='http://127.0.0.1:5173/api/finance/connections/gmail/callback/')
VAPID_PUBLIC_KEY = env('VAPID_PUBLIC_KEY', default='')
VAPID_PRIVATE_KEY = env('VAPID_PRIVATE_KEY', default='')
VAPID_SUBJECT = env('VAPID_SUBJECT', default='mailto:admin@example.com')
TESSERACT_CMD = env('TESSERACT_CMD', default='')

# Notification Settings
NOTIFICATION_DAYS_BEFORE = env.int('NOTIFICATION_DAYS_BEFORE', default=3)
SITE_URL = env('SITE_URL', default='http://127.0.0.1:5173')
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=SITE_URL.startswith('https://'))
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=SESSION_COOKIE_SECURE)
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=False)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
if env.bool('TRUST_PROXY_HTTPS_HEADER', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
REDIS_URL = env('REDIS_URL', default='')
HAS_CHANNELS = True
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
    }
