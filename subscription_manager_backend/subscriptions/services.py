import logging
from datetime import UTC, date, datetime, time, timedelta
from collections import defaultdict
from copy import copy
from decimal import Decimal
from typing import NamedTuple
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from subly.emailing import email_subject, frontend_url

from .models import ChargeShare, NotificationLog, Subscription, Transaction
from .notifications import create_notification

logger = logging.getLogger(__name__)


def effective_renewal_date(subscription, today):
    if subscription.renewal_date and subscription.renewal_date >= today:
        return subscription.renewal_date
    return subscription.calculate_renewal_date(today=today)


def next_billing_date(subscription, today):
    day = effective_renewal_date(subscription, today)
    if day and subscription.bills_on(day):
        return day
    if day and subscription.resume_on and day < subscription.resume_on:
        day = subscription.calculate_renewal_date(today=subscription.resume_on)
        if day and subscription.bills_on(day):
            return day
    return None


def _next_renewal(subscription, day):
    if day == date.max:
        return None
    return subscription.calculate_renewal_date(today=day + timedelta(days=1))


def renewals_between(subscription, first, last, *, use_cursor=True):
    day = effective_renewal_date(subscription, first) if use_cursor else subscription.calculate_renewal_date(today=first)
    while day and first <= day <= last:
        if subscription.bills_on(day):
            yield day
        following = _next_renewal(subscription, day)
        if following is None or following <= day:
            break
        day = following


class ScheduledOccurrence(NamedTuple):
    day: date
    subscription: Subscription
    amount: Decimal
    currency: str
    service: str


def scheduled_occurrences(subscriptions, first, last):
    """Combine visible, outstanding recorded bills with forecast renewals."""
    plans = {sub.pk: sub for sub in subscriptions if sub.configured_status != 'cancelled'}
    recorded = set()
    rows = Transaction.objects.filter(
        subscription_id__in=plans, source=Transaction.SOURCE_RENEWAL,
        charged_for_date__range=(first, last),
    ).values_list('subscription_id', 'team_id', 'user_id', 'charged_for_date',
                  'payment_status', 'amount', 'currency', 'service_name_snapshot').order_by()
    for sub_id, team_id, user_id, day, status, amount, currency, service in rows:
        sub = plans[sub_id]
        if team_id != sub.team_id or (team_id is None and user_id != sub.user_id):
            continue
        recorded.add((sub_id, day))
        if status == Transaction.PaymentStatus.SCHEDULED:
            yield ScheduledOccurrence(day, sub, amount, currency, service)
    for sub in plans.values():
        for day in renewals_between(sub, first, last):
            if (sub.pk, day) not in recorded:
                yield ScheduledOccurrence(day, sub, sub.share_on(day), sub.currency, sub.service_name)


def _record_charge(subscription, day):
    charge, created = Transaction.objects.get_or_create(
        subscription=subscription, charged_for_date=day, source=Transaction.SOURCE_RENEWAL,
        defaults={
            'user_id': subscription.user_id, 'team_id': subscription.team_id, 'shares_captured': True,
            'service_name_snapshot': subscription.service_name, 'currency': subscription.currency,
            'amount': subscription.share_on(day),
        },
    )

    if created and subscription.is_shared:
        price = subscription.price_on(day)
        ChargeShare.objects.bulk_create([
            ChargeShare(charge=charge, name=person.name, member_id=person.member_id,
                        amount=share)
            for person, share in subscription.participant_shares(price)
        ])
    return charge, created


@transaction.atomic
def record_due_charge_for_subscription(subscription, charge_date=None):
    """Record today's charge when creating a subscription."""
    if not subscription or not subscription.pk:
        return None, False
    day = charge_date or timezone.localdate()
    current = Subscription.objects.select_for_update().filter(pk=subscription.pk, status='active').first()
    if current is None or not current.bills_on(day) or effective_renewal_date(current, day) != day:
        return None, False
    result = _record_charge(current, day)
    subscription.renewal_date = _next_renewal(current, day)
    Subscription.objects.filter(pk=current.pk).update(renewal_date=subscription.renewal_date)
    return result


@transaction.atomic
def catch_up_charges(subscription_id, through, *, dry_run=False):
    """Advance the stored billing cursor only after every due charge is recorded."""
    sub = Subscription.objects.select_for_update().filter(pk=subscription_id, status__in=['active', 'paused']).first()
    if sub is None:
        return 0, 0
    # A missing legacy cursor has no reliable unbilled start date.
    day = sub.renewal_date or sub.calculate_renewal_date(today=through)
    created = existing = 0
    while day and day <= through:
        if not sub.bills_on(day):
            day = _next_renewal(sub, day)
            continue
        if dry_run:
            new = not Transaction.objects.filter(subscription=sub, charged_for_date=day, source='renewal').exists()
        else:
            _, new = _record_charge(sub, day)
        if new:
            created += 1
        else:
            existing += 1
        following = _next_renewal(sub, day)
        if following is not None and following <= day:
            raise ValueError('Invalid billing cycle.')
        day = following
    if not dry_run:
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=day)
    return created, existing


class BillingService:
    @staticmethod
    def get_due_renewals(target_date=None):
        through = target_date or timezone.localdate()
        return Subscription.objects.filter(status__in=['active', 'paused']).filter(
            Q(renewal_date__isnull=True) | Q(renewal_date__lte=through)
        )

    @staticmethod
    def record_renewal_charges(target_date=None, dry_run=False):
        instant = timezone.now()
        # Any payer's local day is at most one day ahead of the UTC date.
        # An explicit backfill deliberately uses its supplied date for all payers.
        latest = target_date or instant.date() + timedelta(days=1)
        results = {'date': target_date or instant.date(), 'total': 0, 'created': 0, 'existing': 0, 'errors': 0}
        due = BillingService.get_due_renewals(latest).select_related('user').only(
            'renewal_date', 'user__timezone',
        )
        for sub in list(due):
            try:
                through = target_date or instant.astimezone(_user_zone(sub.user)).date()
                if sub.renewal_date and sub.renewal_date > through:
                    continue
                created, existing = catch_up_charges(sub.pk, through, dry_run=dry_run)
                results['created'] += created
                results['existing'] += existing
                results['total'] += created + existing
            except Exception:
                logger.exception('Failed to record charges for subscription=%s', sub.pk)
                results['errors'] += 1
        return results


def _recipients(subscription):
    if subscription.team_id:
        return [member.user for member in subscription.team.memberships.all() if member.user.is_active]
    return [subscription.user] if subscription.user.is_active else []


def _user_zone(user):
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _reminder_event_instant(sub, day, zone):
    return datetime.combine(day, sub.renewal_time or time(15), zone).astimezone(UTC)


def _due_events(sub, user, offsets, instant, timed):
    """Recover the most recent due offset for each still-actionable event."""
    zone = _user_zone(user)
    today = instant.astimezone(zone).date()
    last = today + timedelta(days=max(offsets))
    events = [(day, 'renewal_reminder') for day in renewals_between(sub, today, last, use_cursor=False)]
    if sub.cancel_by_date and today <= sub.cancel_by_date <= last:
        events.append((sub.cancel_by_date, 'cancellation_deadline'))
    for day, kind in events:
        if _reminder_event_instant(sub, day, zone) < instant:
            continue
        for offset in sorted(offsets):
            due_day = day - timedelta(days=offset)
            due_at = _reminder_event_instant(sub, due_day, zone)
            if (timed and due_at <= instant) or (not timed and due_day <= today):
                yield day, kind, offset
                break


def _reminder_subscriptions():
    return Subscription.objects.filter(
        Q(status='active') | Q(status='paused', resume_on__isnull=False),
        reminders_enabled=True,
    ).exclude(cancellation_state='confirmed').select_related('user', 'team')


def _matches_reminder_event(sub, day, kind):
    if kind == 'cancellation_deadline':
        return sub.cancel_by_date == day
    return sub.bills_on(day) and sub.calculate_renewal_date(today=day) == day


def reminder_is_current(notification):
    """Revalidate scheduled reminders after quiet hours, retries or digest delays."""
    kinds = {'renewal.reminder': 'renewal_reminder', 'cancellation.reminder': 'cancellation_deadline'}
    kind = kinds.get(notification.event_type)
    if kind is None:
        return True
    # Portable restores retain reminders as history, without a live subscription.
    if notification.subscription_id is None:
        return False
    sub = _reminder_subscriptions().filter(pk=notification.subscription_id).first()
    if sub is None or sub.team_id != notification.team_id:
        return False
    if sub.team_id:
        if not sub.team.memberships.filter(user_id=notification.recipient_id).exists():
            return False
    elif sub.user_id != notification.recipient_id:
        return False
    metadata = notification.metadata
    try:
        day = date.fromisoformat(metadata['renewal_date'])
    except (KeyError, TypeError, ValueError):
        return False
    offset = metadata.get('days_before')
    if not isinstance(offset, int):
        return False
    if _reminder_event_instant(sub, day, _user_zone(notification.recipient)) < timezone.now():
        return False
    offsets = set(sub.offsets.values_list('days_before', flat=True)) or {settings.NOTIFICATION_DAYS_BEFORE}
    return offset in offsets and _matches_reminder_event(sub, day, kind)


def _current_reminder(selected, kind, days_before):
    # Sending can lag selection. Recheck the scope, schedule and opt-in before
    # reserving an event, keeping the selected event date independent of billing's cursor.
    sub = _reminder_subscriptions().filter(pk=selected.pk, user_id=selected.user_id, team_id=selected.team_id).first()
    day = selected.renewal_date
    if sub is None or day is None:
        return None
    if hasattr(selected, '_due_recipients'):
        offsets = set(sub.offsets.values_list('days_before', flat=True)) or {settings.NOTIFICATION_DAYS_BEFORE}
        if days_before not in offsets or selected.renewal_time != sub.renewal_time:
            return None
    if not _matches_reminder_event(sub, day, kind):
        return None
    sub.renewal_date = day
    sub.cost = sub.price_on(day)
    return sub


class NotificationService:
    """Service for handling subscription notifications."""

    @staticmethod
    def send_renewal_reminder(subscription, days_before=3):
        """Send a renewal reminder email for a subscription."""
        try:
            due_members = getattr(subscription, '_due_recipients', None)
            kind = getattr(subscription, '_reminder_kind', 'renewal_reminder')
            subscription = _current_reminder(subscription, kind, days_before)
            if subscription is None:
                return False
            if subscription.team_id:
                members = subscription.team.memberships.select_related('user').filter(user__is_active=True)
                if due_members is not None:
                    members = members.filter(user_id__in=[user.pk for user in due_members])
                recipients = [member.user for member in members]
            else:
                recipients = [subscription.user] if subscription.user.is_active else []
            if not recipients:
                return False
            if kind == 'cancellation_deadline':
                label = 'Cancellation deadline'
            elif subscription.trial_end_date == subscription.renewal_date:
                label = 'Trial ends and billing begins'
            else:
                label = 'Renewal reminder'
            key = dict(subscription=subscription, notification_type=kind,
                       renewal_date=subscription.renewal_date, days_before=days_before)
            claim = uuid4()
            pending = []
            now = timezone.now()
            # A stopped worker may leave a claim before SMTP acknowledges delivery.
            stale_before = now - timedelta(seconds=max(600, 4 * settings.EMAIL_TIMEOUT))
            with transaction.atomic():
                if NotificationLog.objects.filter(**key, recipient__isnull=True).exists():
                    return False
                for user in sorted(recipients, key=lambda user: user.pk):
                    if not user.email:
                        continue
                    log, created = NotificationLog.objects.get_or_create(
                        **key, recipient=user, defaults={'delivery_claim': claim},
                    )
                    if created or NotificationLog.objects.filter(
                        pk=log.pk, delivery_claim__isnull=False, sent_at__lt=stale_before,
                    ).update(delivery_claim=claim, sent_at=now):
                        pending.append(user)
            reservations = NotificationLog.objects.filter(**key, delivery_claim=claim)
            if not pending:
                return False
            from finance.delivery import immediate_email
            if subscription.team_id:
                link_url = reverse('accounts:team_detail', args=[subscription.team_id])
            else:
                link_url = reverse('subscriptions:update', args=[subscription.pk])

            failure = None
            delivered = False
            for recipient in pending:
                reservation = reservations.filter(recipient=recipient)
                try:
                    # Large teams may outlive the original claim window. Send
                    # only while we still own this recipient's reservation.
                    if not reservation.update(sent_at=timezone.now()):
                        continue
                    immediate = immediate_email(recipient)
                    if immediate:
                        context = {
                            'user': recipient, 'subscription': subscription, 'event_label': label,
                            'subscription_url': frontend_url(link_url),
                            'preferences_url': frontend_url('/planning/alerts/'),
                        }
                        accepted = send_mail(
                            subject=email_subject('emails/renewal_reminder_subject.txt', context),
                            message=render_to_string('emails/renewal_reminder.txt', context),
                            from_email=settings.DEFAULT_FROM_EMAIL,
                            recipient_list=[recipient.email],
                            html_message=render_to_string('emails/renewal_reminder.html', context),
                            fail_silently=False,
                        )
                        if not accepted:
                            raise RuntimeError('Email backend did not send the renewal reminder.')
                    with transaction.atomic():
                        if not reservation.select_for_update().exists():
                            continue
                        reservation.update(delivery_claim=None, sent_at=timezone.now())
                        create_notification(
                            recipient=recipient,
                            team=subscription.team,
                            subscription=subscription,
                            event_type='cancellation.reminder' if kind == 'cancellation_deadline' else 'renewal.reminder',
                            title=f"{label}: {subscription.service_name}",
                            body=f"{label} on {subscription.renewal_date:%Y-%m-%d}.",
                            link_url=link_url,
                            metadata={
                                'days_before': days_before,
                                'renewal_date': subscription.renewal_date.isoformat(),
                            },
                            send_email_alert=not immediate,
                        )
                    delivered = True
                except Exception as exc:
                    # Keep successful members confirmed even if another address fails.
                    reservation.delete()
                    failure = failure or exc
            if failure:
                raise failure

            logger.info(
                "Renewal reminder sent for %s",
                subscription.service_name,
            )
            return delivered

        except Exception:
            logger.exception("Failed to send renewal reminder")
            raise

    @staticmethod
    def get_subscriptions_due_for_notification(target_time=None, days_before=None, *, now=None):
        """Select reminders using each recipient's local calendar date and renewal time."""
        instant = now or timezone.now()
        if isinstance(target_time, datetime):
            instant = target_time
        elif target_time is not None:
            instant = datetime.combine(timezone.localdate(instant), target_time, timezone.get_current_timezone())
        instant = instant.astimezone(UTC)
        horizon = days_before if days_before is not None else max(30, settings.NOTIFICATION_DAYS_BEFORE)
        # Billing can already have advanced the cursor while a recipient west of UTC
        # is still on their reminder day. Match the calendar schedule independently.
        subscriptions = _reminder_subscriptions().filter(
            Q(start_date__lte=instant.date() + timedelta(days=horizon + 1)) |
            Q(cancel_by_date__lte=instant.date() + timedelta(days=horizon + 1)),
        ).prefetch_related('offsets', 'team__memberships__user')
        due = []
        for sub in subscriptions:
            offsets = {row.days_before for row in sub.offsets.all()} or {settings.NOTIFICATION_DAYS_BEFORE}
            if days_before is not None:
                offsets &= {days_before}
            if not offsets:
                continue
            groups = defaultdict(list)
            for user in _recipients(sub):
                for event in _due_events(sub, user, offsets, instant, target_time is not None):
                    groups[event].append(user)
            for (renewal, kind, offset), recipients in groups.items():
                scheduled_sub = copy(sub)
                scheduled_sub.renewal_date = renewal
                scheduled_sub.cost = sub.price_on(renewal)
                scheduled_sub.user_cost = sub.share_on(renewal)
                scheduled_sub._reminder_kind = kind
                scheduled_sub._due_recipients = recipients
                due.append((scheduled_sub, offset))
        return due

    @staticmethod
    def send_batch_notifications(target_time=None, dry_run=False, days_before=None):
        """Send notifications for all subscriptions due today based on offsets."""
        notifications_to_send = NotificationService.get_subscriptions_due_for_notification(
            target_time,
            days_before=days_before,
        )

        results = {
            'sent': 0,
            'skipped': 0,
            'errors': 0,
            'total': len(notifications_to_send),
        }

        for subscription, offset_days in notifications_to_send:
            try:
                if dry_run:
                    results['sent'] += 1
                    continue

                was_sent = NotificationService.send_renewal_reminder(subscription, offset_days)
                if was_sent:
                    results['sent'] += 1
                else:
                    results['skipped'] += 1
            except Exception:
                results['errors'] += 1
                logger.exception(
                    "Failed to send notification for subscription=%s at offset=%s",
                    subscription.id,
                    offset_days,
                )

        return results
