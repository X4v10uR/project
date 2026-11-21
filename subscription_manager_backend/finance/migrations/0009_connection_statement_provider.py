from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('finance', '0008_job_health_alert')]
    operations = [
        migrations.AlterField(
            model_name='connection',
            name='provider',
            field=models.CharField(max_length=10, choices=[
                ('plaid', 'Plaid'), ('gmail', 'Gmail'), ('statement', 'Bank statement'),
            ]),
        ),
    ]
