from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Team, TeamInvite, TeamMembership, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_staff', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    list_filter = ['is_staff', 'is_active', 'is_superuser']
    ordering = ['email']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profile', {'fields': (
            'first_name', 'last_name', 'display_name', 'bio', 'profile_photo',
            'avatar_choice', 'avatar_background', 'timezone', 'preferred_currency',
        )}),
        ('Billing and preferences', {'fields': (
            'subscription_plan', 'plan_status', 'plan_renews_on',
            'product_updates_enabled', 'marketing_emails_enabled',
        )}),
        *DjangoUserAdmin.fieldsets[2:],
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'usable_password', 'password1', 'password2')}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj and not request.user.is_superuser:
            return ((None, {'fields': ('email', 'first_name', 'last_name', 'is_active')}),)
        return super().get_fieldsets(request, obj)

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_by', 'created_at']
    search_fields = ['name', 'created_by__email']
    list_filter = ['created_at']


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ['team', 'user', 'role', 'invited_by', 'joined_at']
    search_fields = ['team__name', 'user__email', 'invited_by__email']
    list_filter = ['role', 'joined_at']


@admin.register(TeamInvite)
class TeamInviteAdmin(admin.ModelAdmin):
    list_display = [
        'team',
        'email',
        'role',
        'invited_by',
        'created_at',
        'expires_at',
        'accepted_at',
        'revoked_at',
    ]
    search_fields = ['team__name', 'email', 'invited_by__email']
    list_filter = ['role', 'created_at', 'expires_at', 'accepted_at', 'revoked_at']
