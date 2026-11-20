from django.contrib import admin

from .models import ScheduledJobStatus


@admin.register(ScheduledJobStatus)
class ScheduledJobStatusAdmin(admin.ModelAdmin):
    list_display = ('job', 'succeeded', 'last_finished_at', 'last_succeeded_at')
    ordering = ('job',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
