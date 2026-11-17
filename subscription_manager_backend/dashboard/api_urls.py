from django.urls import path

from . import api_views

app_name = 'dashboard_api'

urlpatterns = [
    path('history/', api_views.charge_history, name='history'),
    path('', api_views.dashboard_data, name='home'),
    path('balance/adjust/', api_views.adjust_balance, name='adjust_balance'),
    path('notifications/', api_views.notifications, name='notifications'),
    path('notifications/unread-count/', api_views.unread_count, name='unread_count'),
    path('notifications/read-all/', api_views.mark_all_read, name='read_all'),
    path('notifications/<int:pk>/read/', api_views.mark_read, name='read'),
]
