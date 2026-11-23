import logging
from functools import partial

from asgiref.sync import async_to_sync
try:
    from channels.layers import get_channel_layer
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    def get_channel_layer():
        return None
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import timezone
from subly.emailing import email_subject, frontend_url

from .models import InAppNotification

logger = logging.getLogger(__name__)


def visible_notifications(user):
    return InAppNotification.objects.filter(recipient=user).exclude(
        notificationdelivery__snoozed_until__gt=timezone.now()
    )


def recent_notifications(user):
    return visible_notifications(user).select_related('team').annotate(
        latest=Coalesce('last_reminded_at', 'created_at')
    ).order_by('-latest', '-pk')


def notification_unread_count(user):
    return visible_notifications(user).filter(is_read=False).count()


def mark_all_notifications_read(user):
    unread = visible_notifications(user).filter(is_read=False)
    if unread.update(is_read=True, read_at=timezone.now()):
        push_bulk_read(user)


def serialize_notification(notification):
    return {
        "id": notification.pk,
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "link_url": notification.link_url,
        "is_read": notification.is_read,
        "created_at": (notification.last_reminded_at or notification.created_at).isoformat(),
        "team": notification.team.name if notification.team_id else None,
        "subscription_id": notification.subscription_id,
    }


def _send_group_event(user_id, event_type, payload):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    group_name = f"notifications_user_{user_id}"
    try:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": event_type,
                **payload,
            },
        )
    except Exception:
        logger.exception("Failed to publish websocket notification event")


def push_created(notification):
    _send_group_event(
        notification.recipient_id,
        "notification.created",
        {
            "notification": serialize_notification(notification),
            "unread_count": notification_unread_count(notification.recipient),
        },
    )


def push_updated(notification):
    _send_group_event(
        notification.recipient_id,
        "notification.updated",
        {
            "notification_id": notification.pk,
            "is_read": notification.is_read,
            "unread_count": notification_unread_count(notification.recipient),
        },
    )


def push_bulk_read(user):
    _send_group_event(
        user.pk,
        "notification.bulk_read",
        {
            "unread_count": notification_unread_count(user),
        },
    )


def _send_notification_email(notification):
    recipient = notification.recipient
    context = {
        "notification": notification,
        "recipient": recipient,
        "notification_url": frontend_url(notification.link_url),
    }
    subject = email_subject("emails/subscription_event_subject.txt", context)
    message = render_to_string("emails/subscription_event.txt", context)
    html_message = render_to_string("emails/subscription_event.html", context)
    sent = send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient.email],
        html_message=html_message,
        fail_silently=False,
    )
    if not sent:
        raise RuntimeError('Email backend did not send the notification.')


def _deliver_notification(notification, *, send_email_alert):
    push_created(notification)
    from finance.delivery import route_notification
    route_notification(notification, send_email_alert)


def create_notification(
    *,
    recipient,
    actor=None,
    team=None,
    subscription=None,
    event_type,
    title,
    body="",
    link_url="",
    metadata=None,
    send_email_alert=False,
):
    notification = InAppNotification.objects.create(
        recipient=recipient,
        actor=actor,
        team=team,
        subscription=subscription,
        event_type=event_type,
        title=title,
        body=body,
        link_url=link_url or "",
        metadata=metadata or {},
    )
    transaction.on_commit(
        partial(_deliver_notification, notification, send_email_alert=send_email_alert),
        using=notification._state.db,
    )
    return notification


def create_team_notifications(
    *,
    team,
    actor=None,
    subscription=None,
    event_type,
    title,
    body="",
    link_url="",
    metadata=None,
    send_email_alert=False,
):
    memberships = team.memberships.select_related("user").all()
    actor_id = actor.pk if actor else None
    notifications = []
    for membership in memberships:
        if actor_id and membership.user_id == actor_id:
            continue
        notifications.append(
            create_notification(
                recipient=membership.user,
                actor=actor,
                team=team,
                subscription=subscription,
                event_type=event_type,
                title=title,
                body=body,
                link_url=link_url,
                metadata=metadata,
                send_email_alert=send_email_alert,
            )
        )
    return notifications
