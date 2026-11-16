import hashlib

from django.db import migrations
from django.utils import timezone


INVITE_PREFIX = '/accounts/invites/accept/'


def scrub_links(apps, schema_editor):
    alias = schema_editor.connection.alias
    Notification = apps.get_model('subscriptions', 'InAppNotification')
    Invite = apps.get_model('accounts', 'TeamInvite')
    notifications = Notification.objects.using(alias).filter(
        event_type='team.invite.received', link_url__startswith=INVITE_PREFIX,
    )
    now = timezone.now()
    for notification in notifications.only('link_url').iterator(chunk_size=200):
        token = notification.link_url.removeprefix(INVITE_PREFIX).rstrip('/')
        Invite.objects.using(alias).filter(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            accepted_at__isnull=True,
            revoked_at__isnull=True,
            expires_at__gt=now,
        ).update(revoked_at=now)
    notifications.update(link_url='/accounts/teams/')


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0005_user_avatar_background'),
        ('subscriptions', '0014_subscription_display_color'),
    ]
    operations = [migrations.RunPython(scrub_links, migrations.RunPython.noop)]
