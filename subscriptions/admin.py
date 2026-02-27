from django.contrib import admin
from .models import (
    InAppNotification,
    NotificationLog,
    Subscription,
    TeamSubscriptionRequest,
    Transaction,
)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['service_name', 'user', 'team', 'cost', 'currency', 'billing_cycle', 'renewal_date', 'renewal_time', 'status']
    list_filter = ['status', 'billing_cycle', 'category', 'created_at']
    search_fields = ['service_name', 'user__email', 'category']
    date_hierarchy = 'renewal_date'
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'team', 'service_name', 'category')
        }),
        ('Billing Details', {
            'fields': ('cost', 'plan_name', 'currency', 'billing_cycle')
        }),
        ('Dates & Times', {
            'fields': ('start_date', 'renewal_date', 'renewal_time', 'status')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['subscription', 'notification_type', 'sent_at', 'renewal_date']
    list_filter = ['notification_type', 'sent_at']
    search_fields = ['subscription__service_name', 'subscription__user__email']
    date_hierarchy = 'sent_at'
    readonly_fields = ['sent_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subscription', 'subscription__user')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'service_name_snapshot',
        'user',
        'amount',
        'currency',
        'charged_for_date',
        'source',
        'charged_at',
    ]
    list_filter = ['source', 'currency', 'charged_for_date']
    search_fields = ['service_name_snapshot', 'user__email', 'subscription__service_name']
    date_hierarchy = 'charged_for_date'
    readonly_fields = ['charged_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'subscription')


@admin.register(TeamSubscriptionRequest)
class TeamSubscriptionRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'team',
        'requested_by',
        'status',
        'reviewed_by',
        'reviewed_at',
        'created_at',
    ]
    list_filter = ['status', 'created_at', 'reviewed_at']
    search_fields = ['team__name', 'requested_by__email', 'reviewed_by__email']


@admin.register(InAppNotification)
class InAppNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'recipient',
        'event_type',
        'team',
        'subscription',
        'is_read',
        'created_at',
    ]
    list_filter = ['event_type', 'is_read', 'created_at']
    search_fields = ['recipient__email', 'title', 'body', 'team__name']
