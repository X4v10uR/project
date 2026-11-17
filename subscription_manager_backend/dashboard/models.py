from django.conf import settings
from django.db import models


class BalanceAdjustment(models.Model):
    class Scope(models.TextChoices):
        PERSONAL = 'personal', 'Personal'
        TEAMS = 'teams', 'Teams'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='balance_adjustments',
    )
    scope = models.CharField(max_length=8, choices=Scope.choices, default=Scope.PERSONAL)
    amount = models.DecimalField(max_digits=20, decimal_places=2, default='0.00')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [models.UniqueConstraint(fields=['user', 'scope'], name='unique_balance_scope_per_user')]

    def __str__(self):
        return f"{self.user.email} {self.scope} adjustment {self.amount}"
