from importlib import import_module

from channels.auth import get_user
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return

        self.group_name = f"notifications_user_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            await self.channel_layer.group_discard(group_name, self.channel_name)

    async def send_notification(self, payload):
        # WebSocket authentication is otherwise only checked during the handshake.
        store = import_module(settings.SESSION_ENGINE).SessionStore
        session = store(session_key=self.scope['session'].session_key)
        user = await get_user({'session': session})
        if not user.is_authenticated or user.pk != self.scope['user'].pk:
            await self.close(code=4401)
            return
        await self.send_json(payload)

    async def notification_created(self, event):
        await self.send_notification(
            {
                "type": "notification.created",
                "notification": event.get("notification", {}),
                "unread_count": event.get("unread_count", 0),
            }
        )

    async def notification_updated(self, event):
        await self.send_notification(
            {
                "type": "notification.updated",
                "notification_id": event.get("notification_id"),
                "is_read": event.get("is_read", False),
                "unread_count": event.get("unread_count", 0),
            }
        )

    async def notification_bulk_read(self, event):
        await self.send_notification(
            {
                "type": "notification.bulk_read",
                "unread_count": event.get("unread_count", 0),
            }
        )
