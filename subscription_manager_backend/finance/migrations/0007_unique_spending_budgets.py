from django.db import migrations, models


def consolidate_budgets(apps, schema_editor):
    budgets = apps.get_model('finance', 'SpendingBudget').objects.using(schema_editor.connection.alias)
    duplicates = budgets.values('user_id', 'team_id', 'category', 'currency').annotate(
        count=models.Count('id'), newest=models.Max('id')
    ).filter(count__gt=1)
    for group in list(duplicates):
        # Older restores created extra rows for the same limit. Keep the newest copy.
        identity = {key: group[key] for key in ('user_id', 'team_id', 'category', 'currency')}
        budgets.filter(**identity).exclude(pk=group['newest']).delete()


class Migration(migrations.Migration):
    dependencies = [('finance', '0006_scheduled_job_status')]

    operations = [
        migrations.RunPython(consolidate_budgets, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='spendingbudget',
            constraint=models.UniqueConstraint(fields=['user', 'team', 'category', 'currency'], name='unique_team_spending_budget'),
        ),
        migrations.AddConstraint(
            model_name='spendingbudget',
            constraint=models.UniqueConstraint(fields=['user', 'category', 'currency'], condition=models.Q(team__isnull=True),
                                               name='unique_personal_spending_budget'),
        ),
    ]
