from django.contrib import admin

from .models import Team, TeamInvite, TeamMembership, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_staff', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    list_filter = ['is_staff', 'is_active', 'is_superuser']


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
