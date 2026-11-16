from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0009_subscription_plan_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Transaction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("service_name_snapshot", models.CharField(max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("charged_for_date", models.DateField()),
                ("charged_at", models.DateTimeField(auto_now_add=True)),
                (
                    "source",
                    models.CharField(
                        choices=[("renewal", "Renewal Charge")],
                        default="renewal",
                        max_length=20,
                    ),
                ),
                (
                    "subscription",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="subscriptions.subscription",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-charged_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="transaction",
            constraint=models.UniqueConstraint(
                fields=("subscription", "charged_for_date", "source"),
                name="uniq_transaction_subscription_date_source",
            ),
        ),
    ]
