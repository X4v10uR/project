import base64
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from subscriptions.models import InAppNotification
from .models import NotificationPreference, NotificationDelivery, PushSubscription

logger = logging.getLogger(__name__)


def local_now(user):
    try:
        return timezone.now().astimezone(ZoneInfo(user.timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.now()


def quiet_until(user, preference):
    if not preference or preference.quiet_start is None or preference.quiet_end is None:
        return None
    now = local_now(user)
    start, end, current = preference.quiet_start, preference.quiet_end, now.time().replace(tzinfo=None)
    quiet = start <= current < end if start < end else current >= start or current < end
    if start == end or not quiet:
        return None
    day = now.date() + timedelta(days=1 if start > end and current >= start else 0)
    return datetime.combine(day, end, tzinfo=now.tzinfo)


def immediate_email(user):
    pref = NotificationPreference.objects.filter(user=user).first()
    return not pref or (pref.email_enabled and pref.digest == 'off' and not quiet_until(user, pref))


def send_push(notification):
    from pywebpush import webpush, WebPushException
    success = True
    for sub in PushSubscription.objects.filter(user=notification.recipient):
        try:
            webpush(subscription_info={'endpoint': sub.endpoint, 'keys': sub.keys},
                data=json.dumps({'title': notification.title, 'body': notification.body, 'url': notification.link_url}),
                vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={'sub': settings.VAPID_SUBJECT}, timeout=10)
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404, 410):
                sub.delete()
            else:
                success = False
                logger.warning('Push delivery failed for notification %s', notification.pk)
        except Exception:
            success = False
            logger.warning('Push delivery failed for notification %s', notification.pk)
    return success


def route_notification(notification, send_email_alert):
    from subscriptions.notifications import _send_notification_email
    pref = NotificationPreference.objects.filter(user=notification.recipient).first()
    email = send_email_alert and (not pref or (pref.email_enabled and pref.digest == 'off'))
    push = bool(pref and pref.push_enabled and settings.VAPID_PRIVATE_KEY)
    quiet = quiet_until(notification.recipient, pref)
    if quiet and (email or push):
        NotificationDelivery.objects.update_or_create(notification=notification, defaults={'email': email, 'push': push, 'deliver_after': quiet})
        return
    failed_email = failed_push = False
    if email:
        try:
            _send_notification_email(notification)
        except Exception:
            failed_email = True
            logger.warning('Email delivery queued for notification %s', notification.pk)
    if push:
        failed_push = not send_push(notification)
    if failed_email or failed_push:
        NotificationDelivery.objects.update_or_create(notification=notification,
            defaults={'email': failed_email, 'push': failed_push, 'deliver_after': timezone.now() + timedelta(minutes=5)})


def deliver_queued():
    from subscriptions.notifications import _send_notification_email
    delivered = 0
    ids = list(NotificationDelivery.objects.filter(deliver_after__lte=timezone.now(), attempts__lt=10).values_list('pk', flat=True))
    for pk in ids:
        with transaction.atomic():
            row = NotificationDelivery.objects.select_for_update().select_related('notification__recipient').filter(pk=pk).first()
            if not row or row.deliver_after > timezone.now():
                continue
            n = row.notification
            if n.is_read:
                row.delete()
                continue
            pref = NotificationPreference.objects.filter(user=n.recipient).first()
            quiet = quiet_until(n.recipient, pref)
            if quiet:
                row.deliver_after = quiet
                row.save(update_fields=['deliver_after'])
                continue
            if row.snoozed_until and (n.last_reminded_at is None or n.last_reminded_at < row.snoozed_until):
                n.last_reminded_at = timezone.now()
                n.save(update_fields=['last_reminded_at'])
                from subscriptions.notifications import push_created
                transaction.on_commit(lambda notification=n: push_created(notification))
            try:
                if row.email and (not pref or (pref.email_enabled and pref.digest == 'off')):
                    _send_notification_email(n)
                    row.email = False
                else:
                    row.email = False
                if row.push and pref and pref.push_enabled:
                    row.push = not send_push(n)
                else:
                    row.push = False
            except Exception:
                logger.warning('Notification delivery retry failed: %s', n.pk)
            if row.email or row.push:
                row.attempts += 1
                row.deliver_after = timezone.now() + timedelta(minutes=min(360, 5 * 2 ** row.attempts))
                row.save()
            else:
                row.delete()
                delivered += 1
    return delivered


def send_digests():
    sent = 0
    for pref_id in NotificationPreference.objects.filter(email_enabled=True).exclude(digest='off').values_list('pk', flat=True):
        with transaction.atomic():
            pref = NotificationPreference.objects.select_for_update().select_related('user').get(pk=pref_id)
            now = local_now(pref.user)
            since = pref.last_digest_at
            if quiet_until(pref.user, pref) or now.hour < 9:
                continue
            if since and (now - since).total_seconds() < (86400 if pref.digest == 'daily' else 604800):
                continue
            since = since or timezone.now() - timedelta(days=1 if pref.digest == 'daily' else 7)
            from django.db.models import Q
            rows = InAppNotification.objects.filter(Q(created_at__gt=since) | Q(last_reminded_at__gt=since), recipient=pref.user, is_read=False).exclude(notificationdelivery__snoozed_until__gt=timezone.now()).order_by('created_at')[:100]
            text = '\n\n'.join(f'{n.title}\n{n.body}' for n in rows)
            if text:
                try:
                    send_mail(f'Subly {pref.digest} summary', text + '\n\n' + settings.SITE_URL,
                        settings.DEFAULT_FROM_EMAIL, [pref.user.email], fail_silently=False)
                except Exception:
                    logger.warning('Digest delivery failed for user %s', pref.user_id)
                    continue
                sent += 1
            pref.last_digest_at = timezone.now()
            pref.save(update_fields=['last_digest_at'])
    return sent


class PreferenceInput(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ('email_enabled', 'push_enabled', 'digest', 'quiet_start', 'quiet_end')

    def validate(self, data):
        if bool(data.get('quiet_start')) != bool(data.get('quiet_end')):
            raise serializers.ValidationError('Set both quiet-hour times, or clear both.')
        return data


@api_view(['GET', 'PUT'])
def preferences(request):
    row, _ = NotificationPreference.objects.get_or_create(user=request.user)
    if request.method == 'PUT':
        data = PreferenceInput(row, data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data.get('push_enabled') and not settings.VAPID_PUBLIC_KEY:
            raise serializers.ValidationError('The server has not configured browser push yet.')
        data.save()
    return Response({**PreferenceInput(row).data, 'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'push_configured': bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY), 'timezone': request.user.timezone})


def validate_push(endpoint, keys):
    parsed = urlsplit(endpoint)
    allowed = ('fcm.googleapis.com', 'push.services.mozilla.com', 'notify.windows.com', 'push.apple.com')
    if parsed.scheme != 'https' or not parsed.hostname or not any(parsed.hostname == h or parsed.hostname.endswith('.' + h) for h in allowed) or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise serializers.ValidationError('Unsupported browser push service.')
    for name, length in [('auth', 16), ('p256dh', 65)]:
        try:
            raw = keys[name]
            value = base64.b64decode(raw + '=' * (-len(raw) % 4), altchars=b'-_', validate=True)
            if len(value) != length:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise serializers.ValidationError('Invalid browser subscription keys.')


@api_view(['POST', 'DELETE'])
def push_subscriptions(request):
    endpoint = serializers.URLField(max_length=2048).run_validation(request.data.get('endpoint'))
    if request.method == 'DELETE':
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response(status=204)
    keys = serializers.DictField(child=serializers.CharField(max_length=200)).run_validation(request.data.get('keys'))
    validate_push(endpoint, keys)
    existing = PushSubscription.objects.filter(endpoint=endpoint).first()
    if existing and existing.user_id != request.user.pk:
        # A browser can switch accounts; its active subscription follows its current signed-in user.
        existing.user = request.user
        existing.keys = keys
        existing.session_key = request.session.session_key or ''
        existing.save()
    else:
        PushSubscription.objects.update_or_create(endpoint=endpoint, defaults={'user': request.user, 'keys': keys, 'session_key': request.session.session_key or ''})
    return Response({'subscribed': True})


@api_view(['POST'])
def snooze(request, pk):
    from django.shortcuts import get_object_or_404
    notification = get_object_or_404(InAppNotification, pk=pk, recipient=request.user)
    hours = serializers.IntegerField(min_value=1, max_value=168).run_validation(request.data.get('hours', 24))
    until = timezone.now() + timedelta(hours=hours)
    NotificationDelivery.objects.update_or_create(notification=notification, defaults={'email': True, 'push': True, 'deliver_after': until, 'snoozed_until': until, 'attempts': 0})
    from subscriptions.notifications import push_updated
    push_updated(notification)
    return Response({'snoozed_until': until})
