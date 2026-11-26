from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('finance', '0010_notificationdelivery_push_delivered')]

    operations = [
        migrations.AddField(
            model_name='importedpayment',
            name='acknowledged_charge_difference',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=13, null=True),
        ),
    ]
