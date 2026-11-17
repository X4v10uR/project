from django.db import migrations
from django.db.models import Exists, F, OuterRef
from django.utils import timezone


def schedule_first_charge_on_start(apps, schema_editor):
    Subscription = apps.get_model('subscriptions', 'Subscription')
    Transaction = apps.get_model('subscriptions', 'Transaction')
    database = schema_editor.connection.alias
    first_charge = Transaction.objects.using(database).filter(
        subscription_id=OuterRef('pk'),
        charged_for_date=OuterRef('start_date'),
        source='renewal',
    )
    Subscription.objects.using(database).filter(
        start_date__gte=timezone.localdate(),
        renewal_date__gt=F('start_date'),
    ).exclude(Exists(first_charge)).update(renewal_date=F('start_date'))


class Migration(migrations.Migration):
    dependencies = [('subscriptions', '0015_scrub_invite_notification_links')]

    operations = [migrations.RunPython(schedule_first_charge_on_start, migrations.RunPython.noop)]
