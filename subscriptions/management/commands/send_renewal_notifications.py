from django.core.management.base import BaseCommand
from datetime import timedelta, time
from django.utils import timezone
from subscriptions.models import NotificationLog
from subscriptions.services import NotificationService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send renewal reminder emails for subscriptions with due reminder offsets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-before',
            type=int,
            default=None,
            help='Optional offset filter in days (for example: 3, 7). If omitted, sends all due offsets for today.'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending emails'
        )
        parser.add_argument(
            '--time',
            type=str,
            help='Target time for notifications (HH:MM format, e.g., 15:00). Only sends notifications for subscriptions with matching renewal times.'
        )

    def handle(self, *args, **options):
        days_before = options['days_before']
        dry_run = options['dry_run']
        target_time_str = options.get('time')
        
        # Parse target time if provided
        target_time = None
        if target_time_str:
            try:
                hour, minute = map(int, target_time_str.split(':'))
                target_time = time(hour, minute)
                self.stdout.write(f"Filtering notifications for time: {target_time.strftime('%I:%M %p')}")
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f"Invalid time format: {target_time_str}. Use HH:MM format (e.g., 15:00)")
                )
                return
        
        target_date = None
        if days_before is not None:
            target_date = timezone.localdate() + timedelta(days=days_before)
            self.stdout.write(f"Looking for subscriptions renewing on {target_date}")
        else:
            self.stdout.write("Looking for subscriptions with reminder offsets due today")

        if target_time:
            self.stdout.write(f"Filtering by renewal time around {target_time.strftime('%I:%M %p')}")
        
        # Find active subscriptions that renew on the target date
        subscriptions_to_notify = NotificationService.get_subscriptions_due_for_notification(
            days_before=days_before, 
            target_time=target_time
        )
        
        if not subscriptions_to_notify:
            if target_date is not None:
                message = f"No subscriptions found renewing on {target_date}"
            else:
                message = "No subscriptions found with reminder offsets due today"

            if target_time:
                message += f" at {target_time.strftime('%I:%M %p')}"
            self.stdout.write(self.style.SUCCESS(message))
            return
        
        sent_count = 0
        skipped_count = 0
        error_count = 0
        
        for subscription, offset in subscriptions_to_notify:
            # Check if we've already sent a notification for this renewal
            notification_exists = NotificationLog.objects.filter(
                subscription=subscription,
                notification_type='renewal_reminder',
                renewal_date=subscription.renewal_date,
                days_before=offset
            ).exists()
            
            if notification_exists:
                self.stdout.write(
                    f"Skipping {subscription.service_name} for {subscription.user.email} - already notified (offset: {offset})"
                )
                skipped_count += 1
                continue
            
            try:
                if dry_run:
                    renewal_time_str = ""
                    if subscription.renewal_time:
                        renewal_time_str = f" at {subscription.renewal_time.strftime('%I:%M %p')}"
                    
                    self.stdout.write(
                        f"[DRY RUN] Would send notification for {subscription.service_name} "
                        f"to {subscription.user.email} (renews {subscription.renewal_date}{renewal_time_str}, offset: {offset})"
                    )
                    sent_count += 1
                else:
                    NotificationService.send_renewal_reminder(subscription, days_before=offset)
                    sent_count += 1
                    renewal_time_str = ""
                    if subscription.renewal_time:
                        renewal_time_str = f" at {subscription.renewal_time.strftime('%I:%M %p')}"
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Sent notification for {subscription.service_name} "
                            f"to {subscription.user.email} (renews {subscription.renewal_date}{renewal_time_str}, offset: {offset})"
                        )
                    )
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to send notification for {subscription.service_name} "
                        f"to {subscription.user.email}: {str(e)}"
                    )
                )
                logger.error(f"Email notification error: {str(e)}", exc_info=True)
        
        # Summary
        self.stdout.write("\n" + "="*50)
        if target_date is not None:
            self.stdout.write(f"Summary for {target_date}:")
        else:
            self.stdout.write("Summary for reminder offsets due today:")

        if target_time:
            self.stdout.write(f"Time filter: {target_time.strftime('%I:%M %p')}")
        self.stdout.write(f"  Sent: {sent_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("This was a dry run - no emails were actually sent"))
