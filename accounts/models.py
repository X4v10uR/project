from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
import hashlib

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    PLAN_FREE = 'free'
    PLAN_STARTER = 'starter'
    PLAN_PRO = 'pro'
    PLAN_BUSINESS = 'business'
    PLAN_CHOICES = [
        (PLAN_FREE, 'Free'),
        (PLAN_STARTER, 'Starter'),
        (PLAN_PRO, 'Pro'),
        (PLAN_BUSINESS, 'Business'),
    ]

    PLAN_STATUS_NONE = 'none'
    PLAN_STATUS_TRIALING = 'trialing'
    PLAN_STATUS_ACTIVE = 'active'
    PLAN_STATUS_PAST_DUE = 'past_due'
    PLAN_STATUS_CANCELLED = 'cancelled'
    PLAN_STATUS_CHOICES = [
        (PLAN_STATUS_NONE, 'None'),
        (PLAN_STATUS_TRIALING, 'Trialing'),
        (PLAN_STATUS_ACTIVE, 'Active'),
        (PLAN_STATUS_PAST_DUE, 'Past Due'),
        (PLAN_STATUS_CANCELLED, 'Cancelled'),
    ]

    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.CharField(max_length=280, blank=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    preferred_currency = models.CharField(max_length=3, default='USD')
    subscription_plan = models.CharField(
        max_length=20,
        choices=PLAN_CHOICES,
        default=PLAN_FREE,
    )
    plan_status = models.CharField(
        max_length=20,
        choices=PLAN_STATUS_CHOICES,
        default=PLAN_STATUS_NONE,
    )
    plan_renews_on = models.DateField(null=True, blank=True)
    product_updates_enabled = models.BooleanField(default=True)
    marketing_emails_enabled = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Team(models.Model):
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='owned_teams',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_MEMBER = 'member'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_MEMBER, 'Member'),
    ]

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='team_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    invited_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_memberships_invited',
    )
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ['team', 'user']
        ordering = ['team_id', 'user_id']

    def __str__(self):
        return f"{self.user.email} in {self.team.name} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.ROLE_OWNER


class TeamInvite(models.Model):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='invites',
    )
    email = models.EmailField(db_index=True)
    role = models.CharField(
        max_length=20,
        choices=TeamMembership.ROLE_CHOICES,
        default=TeamMembership.ROLE_MEMBER,
    )
    invited_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='team_invites_sent',
    )
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_invites_accepted',
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite {self.email} -> {self.team.name}"

    @staticmethod
    def hash_token(raw_token):
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def is_usable(self):
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and not self.is_expired()
        )
