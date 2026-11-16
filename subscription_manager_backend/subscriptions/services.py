import logging
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import NotificationLog, Subscription, Transaction
from .notifications import create_notification

logger = logging.getLogger(__name__)


def effective_renewal_date(subscription, today):
    if subscription.renewal_date and subscription.renewal_date >= today:
        return subscription.renewal_date
    return subscription.calculate_renewal_date(today=today)


@transaction.atomic
def record_due_charge_for_subscription(subscription, charge_date=None):
    """
    Record a renewal charge for a single subscription when it is due today.
    Returns (transaction, created).
    """
    if not subscription or not subscription.pk:
        return None, False

    charge_date = charge_date or timezone.localdate()
    current = Subscription.objects.select_for_update().filter(pk=subscription.pk, status='active').first()
    if current is None or effective_renewal_date(current, charge_date) != charge_date:
        return None, False

    amount = current.user_cost if current.is_shared else current.cost
    transaction_defaults = {
        'user_id': current.user_id,
        'service_name_snapshot': current.service_name,
        'amount': amount,
        'currency': current.currency,
    }

    transaction_record, created = Transaction.objects.get_or_create(
        subscription=subscription,
        charged_for_date=charge_date,
        source=Transaction.SOURCE_RENEWAL,
        defaults=transaction_defaults,
    )
    next_renewal = current.calculate_renewal_date(today=charge_date + timedelta(days=1)) if charge_date < date.max else None
    Subscription.objects.filter(pk=current.pk).update(renewal_date=next_renewal)
    subscription.renewal_date = next_renewal
    return transaction_record, created


def _time_in_window(candidate_time, window_start, window_end):
    if window_start <= window_end:
        return window_start <= candidate_time <= window_end

    return candidate_time >= window_start or candidate_time <= window_end


class BillingService:
    """Service for recording renewal charges into transaction history."""

    @staticmethod
    def get_due_renewals(target_date=None):
        charge_date = target_date or timezone.localdate()
        candidate_subs = Subscription.objects.filter(status='active').filter(
            Q(renewal_date__isnull=True) | Q(renewal_date__lte=charge_date)
        )
        return [
            subscription for subscription in candidate_subs
            if effective_renewal_date(subscription, charge_date) == charge_date
        ]

    @staticmethod
    def record_renewal_charges(target_date=None, dry_run=False):
        charge_date = target_date or timezone.localdate()
        due_subscriptions = BillingService.get_due_renewals(target_date=charge_date)

        results = {
            'date': charge_date,
            'total': len(due_subscriptions),
            'created': 0,
            'existing': 0,
            'errors': 0,
        }

        for subscription in due_subscriptions:
            if dry_run:
                exists = Transaction.objects.filter(
                    subscription=subscription,
                    charged_for_date=charge_date,
                    source=Transaction.SOURCE_RENEWAL,
                ).exists()
                if exists:
                    results['existing'] += 1
                else:
                    results['created'] += 1
                continue

            try:
                _, created = record_due_charge_for_subscription(
                    subscription,
                    charge_date=charge_date,
                )
                if created:
                    results['created'] += 1
                else:
                    results['existing'] += 1
            except Exception:
                logger.exception(
                    "Failed to record renewal charge for subscription=%s",
                    subscription.pk,
                )
                results['errors'] += 1

        return results


class NotificationService:
    """Service for handling subscription notifications."""

    @staticmethod
    def send_renewal_reminder(subscription, days_before=3):
        """Send a renewal reminder email for a subscription."""
        try:
            recipients = []
            if subscription.team_id:
                recipients = [
                    membership.user
                    for membership in subscription.team.memberships.select_related('user').all()
                ]
            else:
                recipients = [subscription.user]
            recipient_emails = [user.email for user in recipients if user and user.email]
            if not recipient_emails:
                return False

            # Check if reminders are enabled for this subscription
            if not subscription.reminders_enabled:
                logger.info(
                    "Reminders disabled for %s (User: %s)",
                    subscription.service_name,
                    subscription.user.email,
                )
                return False

            try:
                with transaction.atomic():
                    notification_log = NotificationLog.objects.create(
                        subscription=subscription,
                        notification_type='renewal_reminder',
                        renewal_date=subscription.renewal_date,
                        days_before=days_before,
                    )
            except IntegrityError:
                logger.info(
                    "Notification already reserved for %s at %s days offset to %s",
                    subscription.service_name,
                    days_before,
                    ", ".join(recipient_emails),
                )
                return False

            context = {
                'user': {'first_name': '', 'email': 'there'},
                'subscription': subscription,
                'days_before': days_before,
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            }
            try:
                delivered = send_mail(
                    subject=render_to_string('emails/renewal_reminder_subject.txt', context).strip(),
                    message=render_to_string('emails/renewal_reminder.txt', context),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_emails,
                    html_message=render_to_string('emails/renewal_reminder.html', context),
                    fail_silently=False,
                )
            except Exception:
                NotificationLog.objects.filter(pk=notification_log.pk).delete()
                raise
            if not delivered:
                NotificationLog.objects.filter(pk=notification_log.pk).delete()
                return False

            if subscription.team_id:
                link_url = reverse('accounts:team_detail', args=[subscription.team_id])
            else:
                link_url = reverse('subscriptions:update', args=[subscription.pk])

            for recipient in recipients:
                create_notification(
                    recipient=recipient,
                    team=subscription.team,
                    subscription=subscription,
                    event_type='renewal.reminder',
                    title=f"Renewal reminder: {subscription.service_name}",
                    body=f"Renews in {days_before} day(s).",
                    link_url=link_url,
                    metadata={
                        'days_before': days_before,
                        'renewal_date': subscription.renewal_date.isoformat() if subscription.renewal_date else None,
                    },
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
    def get_subscriptions_due_for_notification(target_time=None, days_before=None):
        """Get subscriptions and offsets that need renewal notifications today."""
        today = timezone.localdate()
        if days_before is not None and days_before > 0:
            horizon_days = days_before
        else:
            horizon_days = max(30, settings.NOTIFICATION_DAYS_BEFORE)
        horizon_date = today + timedelta(days=horizon_days)

        # Subscriptions with reminders enabled
        candidate_subs = Subscription.objects.filter(
            status='active',
            reminders_enabled=True,
        ).filter(
            Q(renewal_date__isnull=True) | Q(renewal_date__lte=horizon_date)
        ).select_related('user').prefetch_related('offsets')

        due_notifications = []

        for subscription in candidate_subs:
            renewal_date = effective_renewal_date(subscription, today)
            if not renewal_date:
                continue
            subscription.renewal_date = renewal_date

            # Calculate days until renewal
            days_until = (renewal_date - today).days

            custom_offsets = {offset.days_before for offset in subscription.offsets.all()}
            matched_offset = None

            if custom_offsets:
                if days_until in custom_offsets:
                    matched_offset = days_until
            elif days_until == settings.NOTIFICATION_DAYS_BEFORE:
                matched_offset = settings.NOTIFICATION_DAYS_BEFORE

            if matched_offset is None:
                continue

            if days_before is not None and matched_offset != days_before:
                continue

            due_notifications.append((subscription, matched_offset))

        # Filter by time if provided
        if target_time:
            time_window_start = (
                datetime.combine(today, target_time) - timedelta(hours=1)
            ).time()
            time_window_end = (
                datetime.combine(today, target_time) + timedelta(hours=1)
            ).time()

            due_notifications = [
                (subscription, offset)
                for subscription, offset in due_notifications
                if (
                    subscription.renewal_time is None
                    or _time_in_window(
                        subscription.renewal_time,
                        time_window_start,
                        time_window_end,
                    )
                )
            ]

        return due_notifications

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
