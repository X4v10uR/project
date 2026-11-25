"""Run Django against a fresh SQLite database for the browser suite."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command

backend = Path(__file__).resolve().parents[3] / 'subscription_manager_backend'
sys.path.insert(0, str(backend))

with TemporaryDirectory(prefix='subly-browser-') as directory:
    os.environ.update(
        DJANGO_SETTINGS_MODULE='subly.settings', SECRET_KEY='isolated-browser-test-key',
        DATABASE_URL=f'sqlite:///{Path(directory).as_posix()}/browser.sqlite3',
        MEDIA_ROOT=directory, PRIVATE_MEDIA_ROOT=str(Path(directory) / 'private'), DEBUG='False', ALLOWED_HOSTS='127.0.0.1,localhost',
        SITE_URL='http://127.0.0.1:14183', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        REDIS_URL='', CSRF_COOKIE_SECURE='False', SESSION_COOKIE_SECURE='False',
        SECURE_SSL_REDIRECT='False', ACCOUNT_PASSWORD_ENCRYPTION_KEY='',
        PLAID_CLIENT_ID='', PLAID_SECRET='', GMAIL_CLIENT_ID='', GMAIL_CLIENT_SECRET='',
        VAPID_PUBLIC_KEY='', VAPID_PRIVATE_KEY='', TESSERACT_CMD='',
    )
    import django
    from django.conf import settings
    # This disposable server only contains browser-test accounts.
    settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
    django.setup()
    call_command('migrate', interactive=False, verbosity=0)
    call_command('runserver', '127.0.0.1:18183', use_reloader=False)
