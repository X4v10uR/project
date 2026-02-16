from django.contrib import admin
from .models import Subscription, NotificationLog

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['service_name', 'user', 'cost', 'currency', 'billing_cycle', 'renewal_date', 'renewal_time', 'status']
    list_filter = ['status', 'billing_cycle', 'category', 'created_at']
    search_fields = ['service_name', 'user__email', 'category']
    date_hierarchy = 'renewal_date'
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'service_name', 'category')
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
