"""Formatting shared by the application's transactional emails."""
from django.conf import settings
from django.template.loader import render_to_string


def email_subject(template_name, context):
    # Names and notification titles can contain line breaks; headers cannot.
    return ' '.join(render_to_string(template_name, context).splitlines()).strip()


def frontend_url(path='/dashboard/'):
    # Notification destinations must remain on our configured frontend origin.
    if (not path.startswith('/') or path.startswith('//') or '\\' in path
            or any(ord(char) < 32 for char in path)):
        path = '/dashboard/'
    return settings.SITE_URL.rstrip('/') + path
