from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home, name='home'),
    path('balance/adjust/', views.adjust_balance, name='adjust_balance'),
    path('notifications/', views.notifications_page, name='notifications_page'),
    path('notifications/api/list/', views.notifications_list_api, name='notifications_list_api'),
    path('notifications/api/unread-count/', views.notifications_unread_count_api, name='notifications_unread_count_api'),
    path('notifications/api/<int:pk>/read/', views.notification_mark_read_api, name='notification_mark_read_api'),
    path('notifications/api/read-all/', views.notifications_mark_all_read_api, name='notifications_mark_all_read_api'),
]
