import uuid
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models


def private_storage():
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def receipt_path(instance, filename):
    return f'receipts/{instance.user_id}/{uuid.uuid4().hex}'


class Receipt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subscription = models.ForeignKey('subscriptions.Subscription', null=True, blank=True, on_delete=models.SET_NULL)
    charge = models.ForeignKey('subscriptions.Transaction', null=True, blank=True, on_delete=models.SET_NULL)
    team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.CASCADE)
    file = models.FileField(storage=private_storage, upload_to=receipt_path)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=80)
    merchant = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    issued_on = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)
    extracted_text = models.TextField(blank=True)
    extraction_status = models.CharField(max_length=30, default='manual')
    created_at = models.DateTimeField(auto_now_add=True)


class ScheduledJobStatus(models.Model):
    job = models.CharField(max_length=64, primary_key=True)
    last_finished_at = models.DateTimeField()
    last_succeeded_at = models.DateTimeField(null=True)
    succeeded = models.BooleanField()

    class Meta:
        verbose_name_plural = 'scheduled job statuses'

    def __str__(self):
        return self.job


class JobHealthAlert(models.Model):
    recipient = models.EmailField(primary_key=True)
    unhealthy_jobs = models.JSONField(default=list)


class Connection(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    provider = models.CharField(max_length=10, choices=[('plaid', 'Plaid'), ('gmail', 'Gmail'), ('statement', 'Bank statement')])
    external_id = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    encrypted_tokens = models.TextField()
    cursor = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    syncing_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'provider', 'external_id'], name='unique_finance_connection')]


class ImportedPayment(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name='payments')
    remote_id = models.CharField(max_length=255)
    merchant = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    paid_on = models.DateField()
    description = models.CharField(max_length=500, blank=True)
    pending = models.BooleanField(default=False)
    removed = models.BooleanField(default=False)
    dismissed = models.BooleanField(default=False)
    subscription = models.ForeignKey('subscriptions.Subscription', null=True, blank=True, on_delete=models.SET_NULL)
    charge = models.ForeignKey('subscriptions.Transaction', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection', 'remote_id'], name='unique_imported_payment'),
            models.UniqueConstraint(fields=['charge'], condition=models.Q(charge__isnull=False), name='unique_matched_charge')]


class ImportedMessage(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE)
    remote_id = models.CharField(max_length=255)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['connection', 'remote_id'], name='unique_imported_message')]


class SpendingBudget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.CASCADE)
    category = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=3)
    monthly_limit = models.DecimalField(max_digits=12, decimal_places=2)
    warning_percent = models.PositiveSmallIntegerField(default=80)
    last_level = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'team', 'category', 'currency'], name='unique_team_spending_budget'),
            models.UniqueConstraint(fields=['user', 'category', 'currency'], condition=models.Q(team__isnull=True),
                                    name='unique_personal_spending_budget'),
        ]


class ExchangeRate(models.Model):
    base = models.CharField(max_length=3)
    quote = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=24, decimal_places=10)
    as_of = models.DateField()
    source = models.CharField(max_length=30, default='Frankfurter')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['base', 'quote'], name='unique_exchange_pair')]


class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    email_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=False)
    digest = models.CharField(max_length=10, choices=[('off', 'Off'), ('daily', 'Daily'), ('weekly', 'Weekly')], default='off')
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)
    last_digest_at = models.DateTimeField(null=True, blank=True)


class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=2048, unique=True)
    keys = models.JSONField()
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationDelivery(models.Model):
    notification = models.OneToOneField('subscriptions.InAppNotification', on_delete=models.CASCADE)
    email = models.BooleanField(default=False)
    push = models.BooleanField(default=False)
    deliver_after = models.DateTimeField()
    snoozed_until = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)


class CalendarFeed(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    token_hash = models.CharField(max_length=64, unique=True)
    scope = models.CharField(max_length=10, default='personal')
    created_at = models.DateTimeField(auto_now_add=True)


class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='finance_activity')
    team = models.ForeignKey('accounts.Team', null=True, blank=True, on_delete=models.CASCADE)
    subscription = models.ForeignKey('subscriptions.Subscription', null=True, blank=True, on_delete=models.SET_NULL)
    service = models.CharField(max_length=100, blank=True)
    action = models.CharField(max_length=100)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
