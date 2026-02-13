from django.db import models
from django.conf import settings
from datetime import date
from dateutil.relativedelta import relativedelta

class Subscription(models.Model):
    BILLING_CYCLE_CHOICES = [
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    service_name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, help_text="e.g. Streaming, Utilities, Software")
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    start_date = models.DateField()
    renewal_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_renewal_date(self):
        if self.billing_cycle == 'weekly':
            return self.start_date + relativedelta(weeks=1)
        elif self.billing_cycle == 'monthly':
            return self.start_date + relativedelta(months=1)
        elif self.billing_cycle == 'yearly':
            return self.start_date + relativedelta(years=1)
        return self.start_date

    def save(self, *args, **kwargs):
        if not self.renewal_date:
            self.renewal_date = self.calculate_renewal_date()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service_name} ({self.user.email})"

    class Meta:
        ordering = ['renewal_date']
