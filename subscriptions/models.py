from django.db import models
from django.conf import settings
from datetime import date, time
from dateutil.relativedelta import relativedelta
from django.core.validators import MinLengthValidator, RegexValidator
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


ACCOUNT_PASSWORD_PREFIX = "enc::"


def _build_account_password_fernet():
    key_material = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))

class Card(models.Model):
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

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
    service_name = models.CharField(max_length=100)
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

        encrypted_password = _build_account_password_fernet().encrypt(
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
        try:
            return _build_account_password_fernet().decrypt(
                encrypted_password.encode("utf-8")
            ).decode("utf-8")
        except InvalidToken:
            return None

    def calculate_renewal_date(self):
        """Calculate the next upcoming renewal date relative to today."""
        if not self.start_date:
            return None
            
        from datetime import date
        today = date.today()
        renewal = self.start_date
        
        # If it's a future subscription, the first renewal is one cycle after start
        if renewal > today:
            if self.billing_cycle == 'weekly':
                return renewal + relativedelta(weeks=1)
            elif self.billing_cycle == 'monthly':
                return renewal + relativedelta(months=1)
            elif self.billing_cycle == 'yearly':
                return renewal + relativedelta(years=1)
            return renewal

        # If it started in the past, increment until we find the next renewal >= today
        while renewal < today:
            if self.billing_cycle == 'weekly':
                renewal += relativedelta(weeks=1)
            elif self.billing_cycle == 'monthly':
                renewal += relativedelta(months=1)
            elif self.billing_cycle == 'yearly':
                renewal += relativedelta(years=1)
            else:
                break
        return renewal

    def save(self, *args, **kwargs):
        # Always ensure renewal_date is synced with start_date and cycle
        self.renewal_date = self.calculate_renewal_date()
        
        # If not shared, user pays full cost
        if not self.is_shared:
            self.user_cost = self.cost

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


class SubscriptionParticipant(models.Model):
    """External participants for shared subscriptions"""
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100)
    share_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} ({self.subscription.service_name})"
