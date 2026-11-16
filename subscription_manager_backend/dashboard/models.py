from django.conf import settings
from django.db import models


class BalanceAdjustment(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='balance_adjustment',
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default='0.00')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.email} adjustment {self.amount}"
