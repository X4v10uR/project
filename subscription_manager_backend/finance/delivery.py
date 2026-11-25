import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from importlib import import_module
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
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
    until = datetime.combine(day, end, tzinfo=now.tzinfo)
    # A clock change can skip this wall time; resume at the first valid minute.
    while until.astimezone(UTC).astimezone(now.tzinfo).replace(tzinfo=None) != until.replace(tzinfo=None):
        until = (until + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # During a repeated hour, the first occurrence may already have passed.
    if until.astimezone(UTC) <= now.astimezone(UTC):
        until = until.replace(fold=1)
    return until


def immediate_email(user):
    pref = NotificationPreference.objects.filter(user=user).first()
    return not pref or (pref.email_enabled and pref.digest == 'off' and not quiet_until(user, pref))


def send_push(notification, *, delivered=None):
    from pywebpush import webpush, WebPushException
    from accounts.models import AccountSecurity

    user = notification.recipient
    session_store = import_module(settings.SESSION_ENGINE).SessionStore
    auth_hashes = [user.get_session_auth_hash(), *user.get_session_auth_fallback_hash()]
    security = AccountSecurity.objects.filter(user=user, enabled=True).first()
    success = True
    delivered = delivered if delivered is not None else set()
    for sub in PushSubscription.objects.filter(user=user):
        session = session_store(session_key=sub.session_key).load()
        session_hash = session.get(HASH_SESSION_KEY)
        # Push access follows the browser's login, including password and MFA revocation.
        authenticated = (
            user.is_active
            and str(session.get(SESSION_KEY)) == str(user.pk)
            and session.get(BACKEND_SESSION_KEY) in settings.AUTHENTICATION_BACKENDS
            and session_hash
            and any(constant_time_compare(session_hash, expected) for expected in auth_hashes)
        )
        if not authenticated or (security and session.get('mfa_revision') != security.revision):
            sub.delete()
            continue
        if sub.pk in delivered:
            continue
        try:
            webpush(subscription_info={'endpoint': sub.endpoint, 'keys': sub.keys},
                data=json.dumps({'title': notification.title, 'body': notification.body, 'url': notification.link_url}),
                vapid_private_key=settings.VAPID_PRIVATE_KEY, vapid_claims={'sub': settings.VAPID_SUBJECT}, timeout=10)
            delivered.add(sub.pk)
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
    from subscriptions.services import reminder_is_current
    if not notification.recipient.is_active or not reminder_is_current(notification):
        return
    pref = NotificationPreference.objects.filter(user=notification.recipient).first()
    email = send_email_alert and (not pref or (pref.email_enabled and pref.digest == 'off'))
    push = bool(pref and pref.push_enabled and settings.VAPID_PRIVATE_KEY)
    quiet = quiet_until(notification.recipient, pref)
    if quiet and (email or push):
        NotificationDelivery.objects.update_or_create(notification=notification, defaults={'email': email, 'push': push, 'deliver_after': quiet})
        return
    failed_email = failed_push = False
    push_delivered = set()
    if email:
        try:
            _send_notification_email(notification)
        except Exception:
            failed_email = True
            logger.warning('Email delivery queued for notification %s', notification.pk)
    if push:
        try:
            failed_push = not send_push(notification, delivered=push_delivered)
        except Exception:
            failed_push = True
            logger.warning('Push delivery queued for notification %s', notification.pk)
    if failed_email or failed_push:
        NotificationDelivery.objects.update_or_create(notification=notification,
            defaults={'email': failed_email, 'push': failed_push, 'push_delivered': sorted(push_delivered),
                      'deliver_after': timezone.now() + timedelta(minutes=5)})


def deliver_queued():
    from subscriptions.notifications import _send_notification_email
    from subscriptions.services import reminder_is_current
    delivered = 0
    ids = list(NotificationDelivery.objects.filter(deliver_after__lte=timezone.now(), attempts__lt=10).values_list('pk', flat=True))
    for pk in ids:
        with transaction.atomic():
            row = NotificationDelivery.objects.select_for_update().select_related('notification__recipient').filter(pk=pk).first()
            if not row or row.deliver_after > timezone.now():
                continue
            n = row.notification
            if n.is_read or not n.recipient.is_active or not reminder_is_current(n):
                row.delete()
                continue
            pref = NotificationPreference.objects.filter(user=n.recipient).first()
            if row.snoozed_until and (n.last_reminded_at is None or n.last_reminded_at < row.snoozed_until):
                n.last_reminded_at = timezone.now()
                n.save(update_fields=['last_reminded_at'])
                from subscriptions.notifications import push_created
                transaction.on_commit(lambda notification=n: push_created(notification))
            quiet = quiet_until(n.recipient, pref)
            if quiet:
                row.deliver_after = quiet
                row.save(update_fields=['deliver_after'])
                continue
            if row.email and (not pref or (pref.email_enabled and pref.digest == 'off')):
                try:
                    _send_notification_email(n)
                    row.email = False
                except Exception:
                    logger.warning('Email delivery retry failed: %s', n.pk)
            else:
                row.email = False
            if row.push and pref and pref.push_enabled:
                push_delivered = set(row.push_delivered)
                try:
                    row.push = not send_push(n, delivered=push_delivered)
                except Exception:
                    logger.warning('Push delivery retry failed: %s', n.pk)
                row.push_delivered = sorted(push_delivered)
            else:
                row.push = False
            if row.email or row.push:
                row.attempts += 1
                row.deliver_after = timezone.now() + timedelta(minutes=min(360, 5 * 2 ** row.attempts))
                row.save()
            else:
                row.delete()
                delivered += 1
    return delivered


def send_digests():
    from subscriptions.services import reminder_is_current
    sent = 0
    eligible = NotificationPreference.objects.filter(email_enabled=True, user__is_active=True).exclude(digest='off')
    for pref_id in eligible.values_list('pk', flat=True):
        with transaction.atomic():
            pref = eligible.select_for_update().select_related('user').filter(pk=pref_id).first()
            if pref is None:
                continue
            cutoff = timezone.now()
            now = local_now(pref.user)
            since = pref.last_digest_at
            interval = timedelta(days=1 if pref.digest == 'daily' else 7)
            if quiet_until(pref.user, pref) or now.hour < 9:
                continue
            if since and now.date() < since.astimezone(now.tzinfo).date() + interval:
                continue
            if since is None:
                # Keep the first retry's window fixed even if delivery fails past
                # tomorrow's rolling lookback window.
                since = cutoff - interval
                pref.last_digest_at = since
                pref.save(update_fields=['last_digest_at'])
            from django.db.models import Q
            rows = InAppNotification.objects.filter(Q(created_at__gt=since) | Q(last_reminded_at__gt=since),
                recipient=pref.user, is_read=False, created_at__lte=cutoff).filter(
                Q(last_reminded_at__isnull=True) | Q(last_reminded_at__lte=cutoff)
            ).exclude(notificationdelivery__snoozed_until__gt=cutoff).order_by('created_at', 'pk')
            text = '\n\n'.join(f'{n.title}\n{n.body}' for n in rows.iterator() if reminder_is_current(n))
            if text:
                try:
                    accepted = send_mail(f'DUES {pref.digest} summary', text + '\n\n' + settings.SITE_URL,
                        settings.DEFAULT_FROM_EMAIL, [pref.user.email], fail_silently=False)
                    if not accepted:
                        raise RuntimeError('Email backend did not send the digest.')
                except Exception:
                    logger.warning('Digest delivery failed for user %s', pref.user_id)
                    continue
                sent += 1
            pref.last_digest_at = cutoff
            pref.save(update_fields=['last_digest_at'])
    return sent


class PreferenceInput(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = ('email_enabled', 'push_enabled', 'digest', 'quiet_start', 'quiet_end')

    def validate(self, data):
        start = data.get('quiet_start', getattr(self.instance, 'quiet_start', None))
        end = data.get('quiet_end', getattr(self.instance, 'quiet_end', None))
        if (start is None) != (end is None):
            raise serializers.ValidationError('Set both quiet-hour times, or clear both.')
        return data


@api_view(['GET', 'PUT'])
@transaction.atomic
def preferences(request):
    row, _ = NotificationPreference.objects.select_for_update().get_or_create(user=request.user)
    if request.method == 'PUT':
        data = PreferenceInput(row, data=request.data)
        data.is_valid(raise_exception=True)
        if data.validated_data.get('push_enabled') and not (settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY):
            raise serializers.ValidationError('The server has not configured browser push yet.')
        data.save()
    return Response({**PreferenceInput(row).data, 'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'push_configured': bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY), 'timezone': request.user.timezone})


def validate_push(endpoint, keys):
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError:
        raise serializers.ValidationError('Unsupported browser push service.')
    allowed = ('fcm.googleapis.com', 'push.services.mozilla.com', 'notify.windows.com', 'push.apple.com')
    if parsed.scheme != 'https' or not parsed.hostname or not any(parsed.hostname == h or parsed.hostname.endswith('.' + h) for h in allowed) or parsed.username or parsed.password or port not in (None, 443) or parsed.fragment:
        raise serializers.ValidationError('Unsupported browser push service.')
    for name, length in [('auth', 16), ('p256dh', 65)]:
        try:
            raw = keys[name]
            value = base64.b64decode(raw + '=' * (-len(raw) % 4), altchars=b'-_', validate=True)
            if len(value) != length:
                raise ValueError()
            if name == 'p256dh':
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), value)
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
@transaction.atomic
def snooze(request, pk):
    from django.shortcuts import get_object_or_404
    notification = get_object_or_404(InAppNotification.objects.select_for_update(), pk=pk, recipient=request.user)
    hours = serializers.IntegerField(min_value=1, max_value=168).run_validation(request.data.get('hours', 24))
    until = timezone.now() + timedelta(hours=hours)
    NotificationDelivery.objects.update_or_create(notification=notification, defaults={'email': True, 'push': True,
        'push_delivered': [], 'deliver_after': until, 'snoozed_until': until, 'attempts': 0})
    notification.is_read = False
    notification.read_at = None
    notification.save(update_fields=['is_read', 'read_at'])
    from subscriptions.notifications import push_updated
    transaction.on_commit(lambda: push_updated(notification))
    return Response({'snoozed_until': until})
