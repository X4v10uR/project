import logging
from decimal import Decimal
from datetime import UTC, date, datetime, time, timedelta
from collections import defaultdict
from copy import copy
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import ChargeShare, NotificationLog, Subscription, Transaction
from .notifications import create_notification

logger = logging.getLogger(__name__)


def effective_renewal_date(subscription, today):
    if subscription.renewal_date and subscription.renewal_date >= today:
        return subscription.renewal_date
    return subscription.calculate_renewal_date(today=today)


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
        people = list(subscription.participants.all())
        cents, remainder = divmod(int(subscription.price_on(day) * 100), len(people) + 1)
        ChargeShare.objects.bulk_create([
            ChargeShare(charge=charge, name=person.name, member_id=person.member_id,
                        amount=Decimal(cents + (index < remainder)).scaleb(-2) if subscription.split_type == 'equal' else person.share_amount or 0)
            for index, person in enumerate(people, 1)
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
        through = target_date or timezone.localdate()
        results = {'date': through, 'total': 0, 'created': 0, 'existing': 0, 'errors': 0}
        ids = BillingService.get_due_renewals(through).values_list('pk', flat=True)
        for subscription_id in list(ids):
            try:
                created, existing = catch_up_charges(subscription_id, through, dry_run=dry_run)
                results['created'] += created
                results['existing'] += existing
                results['total'] += created + existing
            except Exception:
                logger.exception('Failed to record charges for subscription=%s', subscription_id)
                results['errors'] += 1
        return results


def _recipients(subscription):
    if subscription.team_id:
        return [member.user for member in subscription.team.memberships.all()]
    return [subscription.user]


def _user_zone(user):
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _due_events(sub, user, offsets, instant, timed):
    """Recover the most recent due offset for each still-actionable event."""
    zone = _user_zone(user)
    today = instant.astimezone(zone).date()
    last = today + timedelta(days=max(offsets))
    events = [(day, 'renewal_reminder') for day in renewals_between(sub, today, last, use_cursor=False)]
    if sub.cancel_by_date and today <= sub.cancel_by_date <= last:
        events.append((sub.cancel_by_date, 'cancellation_deadline'))
    for day, kind in events:
        local_time = sub.renewal_time or time(15)
        if datetime.combine(day, local_time, zone).astimezone(UTC) < instant:
            continue
        for offset in sorted(offsets):
            due_day = day - timedelta(days=offset)
            due_at = datetime.combine(due_day, local_time, zone).astimezone(UTC)
            if (timed and due_at <= instant) or (not timed and due_day <= today):
                yield day, kind, offset
                break


class NotificationService:
    """Service for handling subscription notifications."""

    @staticmethod
    def send_renewal_reminder(subscription, days_before=3):
        """Send a renewal reminder email for a subscription."""
        try:
            due_members = getattr(subscription, '_due_recipients', None)
            if subscription.team_id:
                members = subscription.team.memberships.select_related('user')
                if due_members is not None:
                    members = members.filter(user_id__in=[user.pk for user in due_members])
                recipients = [member.user for member in members]
            else:
                recipients = [subscription.user]
            if not subscription.reminders_enabled or not recipients:
                return False
            kind = getattr(subscription, '_reminder_kind', 'renewal_reminder')
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
            recipient_emails = [user.email for user in pending]
            from finance.delivery import immediate_email
            immediate_recipients = [user for user in pending if immediate_email(user)]
            recipient_emails = [user.email for user in immediate_recipients]

            context = {
                'user': {'first_name': '', 'email': 'there'},
                'subscription': subscription,
                'event_label': label,
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            }
            try:
                delivered = not recipient_emails or send_mail(
                    subject=render_to_string('emails/renewal_reminder_subject.txt', context).strip(),
                    message=render_to_string('emails/renewal_reminder.txt', context),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_emails,
                    html_message=render_to_string('emails/renewal_reminder.html', context),
                    fail_silently=False,
                )
            except Exception:
                reservations.delete()
                raise
            if not delivered:
                reservations.delete()
                return False

            if subscription.team_id:
                link_url = reverse('accounts:team_detail', args=[subscription.team_id])
            else:
                link_url = reverse('subscriptions:update', args=[subscription.pk])

            with transaction.atomic():
                confirmed = set(reservations.select_for_update().values_list('recipient_id', flat=True))
                reservations.update(delivery_claim=None, sent_at=timezone.now())
                for recipient in pending:
                    if recipient.pk not in confirmed:
                        continue
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
                            'renewal_date': subscription.renewal_date.isoformat() if subscription.renewal_date else None,
                        },
                        send_email_alert=recipient not in immediate_recipients,
                    )

            logger.info(
                "Renewal reminder sent for %s",
                subscription.service_name,
            )
            return True

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
        subscriptions = Subscription.objects.filter(
            Q(start_date__lte=instant.date() + timedelta(days=horizon + 1)) |
            Q(cancel_by_date__lte=instant.date() + timedelta(days=horizon + 1)),
            status='active', reminders_enabled=True,
        ).select_related('user', 'team').prefetch_related('offsets', 'team__memberships__user')
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
