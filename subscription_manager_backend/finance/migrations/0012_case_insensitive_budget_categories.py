from django.db import migrations, models
from django.db.models.functions import Lower


def consolidate_case_variants(apps, schema_editor):
    budgets = apps.get_model('finance', 'SpendingBudget').objects.using(schema_editor.connection.alias)
    budgets = budgets.annotate(category_key=Lower('category'))
    scopes = ('user_id', 'team_id', 'currency', 'category_key')
    duplicates = budgets.order_by().values(*scopes).annotate(
        count=models.Count('pk'), newest=models.Max('pk'),
    ).filter(count__gt=1)
    for group in list(duplicates):
        # The old rows have no edit timestamp; retain the most recently created row.
        budgets.filter(**{key: group[key] for key in scopes}).exclude(pk=group['newest']).delete()


class Migration(migrations.Migration):
    dependencies = [('finance', '0011_importedpayment_acknowledged_charge_difference')]

    operations = [
        migrations.RunPython(consolidate_case_variants, migrations.RunPython.noop),
        migrations.RemoveConstraint('spendingbudget', 'unique_team_spending_budget'),
        migrations.RemoveConstraint('spendingbudget', 'unique_personal_spending_budget'),
        migrations.AddConstraint(
            model_name='spendingbudget',
            constraint=models.UniqueConstraint('user', 'team', Lower('category'), 'currency',
                                               condition=models.Q(team__isnull=False), name='unique_team_spending_budget'),
        ),
        migrations.AddConstraint(
            model_name='spendingbudget',
            constraint=models.UniqueConstraint('user', Lower('category'), 'currency',
                                               condition=models.Q(team__isnull=True), name='unique_personal_spending_budget'),
        ),
    ]
