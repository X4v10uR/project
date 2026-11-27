"""Security checks for production deployment, without changing local defaults."""

from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def check_dues_deployment(app_configs, **kwargs):
    findings = []
    public = Path(settings.MEDIA_ROOT).resolve()
    private = Path(settings.PRIVATE_MEDIA_ROOT).resolve()
    static = Path(settings.STATIC_ROOT).resolve()
    public_roots = [public, static, *(Path(path).resolve() for path in settings.STATICFILES_DIRS)]
    if any(private == root or private in root.parents or root in private.parents for root in public_roots):
        findings.append(Error(
            'Private receipt storage and public media/static storage overlap.',
            hint='Use separate, non-overlapping directories and never expose the private root through the web server.',
            id='dues.E001',
        ))
    try:
        site = urlsplit(settings.SITE_URL)
        secure_origin = (site.scheme == 'https' and bool(site.hostname) and not site.username
                         and site.path in ('', '/') and not site.query and not site.fragment)
    except ValueError:
        secure_origin = False
    if not secure_origin:
        findings.append(Warning(
            'SITE_URL is not an HTTPS origin.',
            hint='Set SITE_URL to the externally reachable HTTPS origin so emails and calendar links use it.',
            id='dues.W001',
        ))
    if settings.SITE_URL.startswith('https://') and not (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE):
        findings.append(Warning(
            'DUES uses an HTTPS SITE_URL with an insecure session or CSRF cookie setting.',
            hint='Set SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE to True for HTTPS deployments.',
            id='dues.W002',
        ))
    key = settings.ACCOUNT_PASSWORD_ENCRYPTION_KEY.strip()
    if not key or key == settings.SECRET_KEY:
        findings.append(Warning(
            'A separate credential encryption key is not configured.',
            hint='Provision a dedicated Fernet key. Migrate existing legacy ciphertexts before retiring fallback keys.',
            id='dues.W003',
        ))
    else:
        try:
            Fernet(key.encode('utf-8'))
        except (TypeError, ValueError):
            findings.append(Error(
                'ACCOUNT_PASSWORD_ENCRYPTION_KEY is not a valid Fernet key.',
                hint='Correct the configuration with your existing key or follow the staged key migration procedure.',
                id='dues.E002',
            ))
    if '*' in settings.ALLOWED_HOSTS:
        findings.append(Warning(
            'DUES accepts all host names.',
            hint='Set ALLOWED_HOSTS to the public DUES host names and validate the Host header at the edge.',
            id='dues.W004',
        ))
    return findings
