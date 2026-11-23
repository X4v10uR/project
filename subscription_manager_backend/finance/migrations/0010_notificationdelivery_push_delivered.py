from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('finance', '0009_connection_statement_provider')]

    operations = [
        migrations.AddField(
            model_name='notificationdelivery',
            name='push_delivered',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
