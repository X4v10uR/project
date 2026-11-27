from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('subscriptions', '0022_team_renewal')]

    operations = [
        migrations.AddField(
            model_name='teamrenewal',
            name='paid_seats',
            field=models.PositiveIntegerField(
                blank=True, null=True, validators=[MinValueValidator(1), MaxValueValidator(1000000)],
            ),
        ),
        migrations.AddField(
            model_name='teamrenewal',
            name='needed_seats',
            field=models.PositiveIntegerField(blank=True, null=True, validators=[MaxValueValidator(1000000)]),
        ),
        migrations.AddField(
            model_name='teamrenewal',
            name='decision_reason',
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
