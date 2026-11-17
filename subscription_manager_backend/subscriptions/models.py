from django.db import models
from django.conf import settings
from datetime import time
from dateutil.relativedelta import relativedelta
from django.core.validators import MinLengthValidator, RegexValidator
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .color_utils import normalize_subscription_display_color


ACCOUNT_PASSWORD_PREFIX = "enc::"


def _build_legacy_account_password_fernet():
    key_material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _build_configured_account_password_fernet():
    raw_key = getattr(settings, "ACCOUNT_PASSWORD_ENCRYPTION_KEY", "")
    if not raw_key:
        return None

    try:
        return Fernet(raw_key.strip().encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "ACCOUNT_PASSWORD_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def _account_password_encrypt_fernet():
    configured = _build_configured_account_password_fernet()
    if configured:
        return configured
    return _build_legacy_account_password_fernet()


def _account_password_decrypt_fernets():
    configured = _build_configured_account_password_fernet()
    if not configured:
        return [_build_legacy_account_password_fernet()]

    fernets = [configured]
    if getattr(settings, "ACCOUNT_PASSWORD_LEGACY_FALLBACK", True):
        fernets.append(_build_legacy_account_password_fernet())
    return fernets

class Card(models.Model):
    THEME_DARK = "dark"
    THEME_NAVY = "navy"
    THEME_FOREST = "forest"
    THEME_PLUM = "plum"
    THEME_ROSE = "rose"
    THEME_CHOICES = [
        (THEME_DARK, "Midnight"),
        (THEME_NAVY, "Ocean"),
        (THEME_FOREST, "Forest"),
        (THEME_PLUM, "Plum"),
        (THEME_ROSE, "Rose"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cards')
    nickname = models.CharField(max_length=50)
    last4 = models.CharField(
        max_length=4, 
        validators=[
            MinLengthValidator(4), 
            RegexValidator(r'^\d{4}$', 'Must be exactly 4 digits')
        ]
    )
    brand = models.CharField(max_length=20, blank=True, null=True)
    theme = models.CharField(max_length=20, choices=THEME_CHOICES, default=THEME_DARK)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_primary=True),
                name="uniq_primary_card_per_user",
            ),
        ]

    def __str__(self):
        brand_display = f" — {self.brand}" if self.brand else ""
        return f"{self.nickname}{brand_display} •••• {self.last4}"

    def get_brand_icon_url(self):
        if not self.brand:
            return None
        
        brand_lower = self.brand.lower().strip()
        
        # Direct mappings to specific SVG URLs
        mappings = {
            'visa': 'https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg',
            'mastercard': 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/mastercard.svg',
            'amex': 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/american-express.svg',
            'american express': 'https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/american-express.svg',
        }
        
        return mappings.get(brand_lower)

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
    team = models.ForeignKey(
        'accounts.Team',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subscriptions',
    )
    service_name = models.CharField(max_length=100)
    display_color = models.CharField(
        max_length=7,
        blank=True,
        default="",
        validators=[
            RegexValidator(
                r"^#[0-9A-Fa-f]{6}$",
                "Enter a valid 6-digit hex color.",
            )
        ],
        help_text="Optional custom light color for subscription cards.",
    )
    plan_name = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. Basic, Premium, Family Plan")
    category = models.CharField(max_length=50, help_text="e.g. Streaming, Utilities, Software")
    billing_cycle = models.CharField(max_length=10, choices=BILLING_CYCLE_CHOICES)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    user_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="The amount the user actually pays")
    is_shared = models.BooleanField(default=False)
    split_type = models.CharField(
        max_length=10, 
        choices=[('equal', 'Equal Split'), ('custom', 'Custom Split')], 
        default='equal'
    )
    currency = models.CharField(max_length=3, default='USD')
    start_date = models.DateField()
    renewal_date = models.DateField(null=True, blank=True)
    renewal_time = models.TimeField(
        null=True, 
        blank=True, 
        default=time(15, 0),  # Default to 3:00 PM
        help_text="Setting the time defines the exact time subscription is ending. Notifications will be sent at this time 3 days before renewal."
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reminders_enabled = models.BooleanField(
        default=True,
        help_text="Whether to send renewal notifications for this subscription."
    )
    card = models.ForeignKey(Card, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    account_email = models.CharField(max_length=255, blank=True, null=True)
    account_password = models.CharField(max_length=512, blank=True, null=True)

    def set_account_password(self, raw_password):
        if not raw_password:
            self.account_password = None
            return

        encrypted_password = _account_password_encrypt_fernet().encrypt(
            raw_password.encode("utf-8")
        ).decode("utf-8")
        self.account_password = f"{ACCOUNT_PASSWORD_PREFIX}{encrypted_password}"

    def get_account_password(self):
        if not self.account_password:
            return None

        if not self.account_password.startswith(ACCOUNT_PASSWORD_PREFIX):
            # Backward compatibility for legacy plaintext rows.
            return self.account_password

        encrypted_password = self.account_password[len(ACCOUNT_PASSWORD_PREFIX) :]
        for fernet in _account_password_decrypt_fernets():
            try:
                return fernet.decrypt(
                    encrypted_password.encode("utf-8")
                ).decode("utf-8")
            except InvalidToken:
                continue
        return None

    def calculate_renewal_date(self, today=None):
        """Calculate the next upcoming renewal date relative to today."""
        start = self.start_date
        if not start:
            return None

        today = today or timezone.localdate()
        if start >= today:
            return start
        try:
            if self.billing_cycle == 'weekly':
                weeks = ((today - start).days + 6) // 7
                return start + relativedelta(weeks=weeks)
            period = {'monthly': 1, 'yearly': 12}.get(self.billing_cycle)
            if not period:
                return start
            elapsed = (today.year - start.year) * 12 + today.month - start.month
            months = elapsed // period * period
            renewal = start + relativedelta(months=months)
            if renewal < today:
                renewal = start + relativedelta(months=months + period)
            return renewal
        except (OverflowError, ValueError):
            # Some legacy records may have a start date near the calendar limit.
            return None

    def save(self, *args, **kwargs):
        # Always ensure renewal_date is synced with start_date and cycle
        existing_subscription = None
        if self.pk:
            existing_subscription = (
                type(self)
                .objects.filter(pk=self.pk)
                .only("start_date", "billing_cycle", "renewal_date")
                .first()
            )

        calculated_renewal_date = self.calculate_renewal_date()
        if (
            existing_subscription
            and existing_subscription.start_date == self.start_date
            and existing_subscription.billing_cycle == self.billing_cycle
            and existing_subscription.renewal_date
            and calculated_renewal_date
            and existing_subscription.renewal_date > calculated_renewal_date
        ):
            calculated_renewal_date = existing_subscription.renewal_date

        self.renewal_date = calculated_renewal_date
        
        # If not shared, user pays full cost
        if not self.is_shared:
            self.user_cost = self.cost

        self.display_color = normalize_subscription_display_color(self.display_color)

        if self.account_password == "":
            self.account_password = None
        elif (
            self.account_password
            and not self.account_password.startswith(ACCOUNT_PASSWORD_PREFIX)
        ):
            self.set_account_password(self.account_password)
        
        if not self.renewal_time:
            self.renewal_time = time(15, 0)
            
        super().save(*args, **kwargs)

    def get_icon_url(self):
        """Generate icon URL from service name"""
        # Common service name mappings
        service_mappings = {
            'chatgpt plus': 'openai',
            'chat gpt': 'openai',
            'openai': 'openai',
            'adobe cc': 'adobe',
            'adobe creative cloud': 'adobe',
            'disney+': 'disney-plus',
            'disney plus': 'disney-plus',
            'amazon prime': 'amazon-prime-video',
            'prime video': 'amazon-prime-video',
            'youtube premium': 'youtube',
            'google drive': 'google-drive',
            'google workspace': 'google-workspace',
            'microsoft 365': 'microsoft-365',
            'office 365': 'microsoft-365',
            'icloud': 'icloud',
            'dropbox': 'dropbox',
            'github': 'github',
            'gitlab': 'gitlab',
            'bitbucket': 'bitbucket',
            'aws': 'amazon-web-services',
            'amazon web services': 'amazon-web-services',
            'google cloud': 'google-cloud',
            'azure': 'microsoft-azure',
            'digital ocean': 'digitalocean',
            'linode': 'linode',
            'vultr': 'vultr',
        }
        
        # Convert service name to lowercase
        service_lower = self.service_name.lower().strip()
        
        # Check if we have a direct mapping
        if service_lower in service_mappings:
            icon_name = service_mappings[service_lower]
        else:
            # Convert service name to icon format
            icon_name = service_lower
            icon_name = icon_name.replace(' ', '-')
            icon_name = icon_name.replace('+', '-plus')
            icon_name = icon_name.replace('&', '-and')
            icon_name = icon_name.replace('.', '')
            icon_name = icon_name.replace('(', '').replace(')', '')
            icon_name = icon_name.replace('_', '-')
        
        return f"https://cdn.jsdelivr.net/gh/selfhst/icons@main/svg/{icon_name}.svg"
    
    def get_fallback_icon(self):
        """Get first letter of service name for fallback"""
        return self.service_name[0].upper() if self.service_name else 'S'

    def __str__(self):
        if self.team_id:
            return f"{self.service_name} ({self.team.name})"
        return f"{self.service_name} ({self.user.email})"

    class Meta:
        ordering = ['renewal_date']


class ReminderOffset(models.Model):
    """Custom reminder offsets for a subscription (e.g., 1 day before, 7 days before)"""
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='offsets')
    days_before = models.IntegerField(default=3)
    
    class Meta:
        unique_together = ['subscription', 'days_before']
        ordering = ['-days_before']

    def __str__(self):
        return f"{self.subscription.service_name} - {self.days_before} days before"


class TeamSubscriptionRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    team = models.ForeignKey(
        'accounts.Team',
        on_delete=models.CASCADE,
        related_name='subscription_requests',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscription_requests',
    )
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_subscription_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    created_subscription = models.OneToOneField(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='origin_request',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Request {self.pk} for {self.team.name} ({self.status})"


class InAppNotification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='in_app_notifications',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications_triggered',
    )
    team = models.ForeignKey(
        'accounts.Team',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='in_app_notifications',
    )
    event_type = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    link_url = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]

    def __str__(self):
        return f"{self.recipient.email}: {self.title}"

    def mark_read(self):
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])


class NotificationLog(models.Model):
    """Track sent notifications to avoid duplicates"""
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=50, default='renewal_reminder')
    sent_at = models.DateTimeField(auto_now_add=True)
    renewal_date = models.DateField()  # The renewal date this notification was for
    days_before = models.IntegerField(default=3) # The offset used for this notification
    
    class Meta:
        unique_together = ['subscription', 'notification_type', 'renewal_date', 'days_before']
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.subscription.service_name} - {self.notification_type} - {self.renewal_date}"


class Transaction(models.Model):
    SOURCE_RENEWAL = "renewal"
    SOURCE_CHOICES = [
        (SOURCE_RENEWAL, "Renewal Charge"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    service_name_snapshot = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    charged_for_date = models.DateField()
    charged_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_RENEWAL,
    )

    class Meta:
        ordering = ["-charged_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "charged_for_date", "source"],
                name="uniq_transaction_subscription_date_source",
            )
        ]

    def __str__(self):
        return (
            f"{self.service_name_snapshot} {self.currency} {self.amount} "
            f"({self.charged_for_date})"
        )


class SubscriptionParticipant(models.Model):
    """External participants for shared subscriptions"""
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100)
    share_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.subscription.service_name})"
