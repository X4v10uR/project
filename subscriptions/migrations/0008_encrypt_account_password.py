import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations, models


ACCOUNT_PASSWORD_PREFIX = "enc::"


def _build_account_password_fernet():
    key_material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_existing_account_passwords(apps, schema_editor):
    Subscription = apps.get_model('subscriptions', 'Subscription')
    fernet = _build_account_password_fernet()

    subscriptions = Subscription.objects.exclude(account_password__isnull=True).exclude(account_password='')
    for subscription in subscriptions.iterator():
        if subscription.account_password.startswith(ACCOUNT_PASSWORD_PREFIX):
            continue

        encrypted_password = fernet.encrypt(
            subscription.account_password.encode("utf-8")
        ).decode("utf-8")
        subscription.account_password = f"{ACCOUNT_PASSWORD_PREFIX}{encrypted_password}"
        subscription.save(update_fields=['account_password'])


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0007_subscription_account_email_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subscription',
            name='account_password',
            field=models.CharField(blank=True, max_length=512, null=True),
        ),
        migrations.RunPython(encrypt_existing_account_passwords, migrations.RunPython.noop),
    ]
