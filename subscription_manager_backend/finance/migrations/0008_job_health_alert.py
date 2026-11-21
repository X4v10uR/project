from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('finance', '0007_unique_spending_budgets')]

    operations = [
        migrations.CreateModel(
            name='JobHealthAlert',
            fields=[
                ('recipient', models.EmailField(max_length=254, primary_key=True, serialize=False)),
                ('unhealthy_jobs', models.JSONField(default=list)),
            ],
        ),
    ]
