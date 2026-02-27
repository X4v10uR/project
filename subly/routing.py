from django.urls import path

from dashboard.consumers import NotificationConsumer


websocket_urlpatterns = [
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
