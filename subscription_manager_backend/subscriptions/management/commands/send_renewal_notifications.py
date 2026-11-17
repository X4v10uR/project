from django.core.management.base import BaseCommand, CommandError
from datetime import time
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
            except ValueError as exc:
                raise CommandError(f"Invalid time format: {target_time_str}. Use HH:MM format (e.g., 15:00).") from exc
        
        self.stdout.write("Checking reminder dates in each recipient's time zone.")

        if target_time:
            self.stdout.write(f"Filtering by renewal time around {target_time.strftime('%I:%M %p')}")
        
        # Find active subscriptions that renew on the target date
        subscriptions_to_notify = NotificationService.get_subscriptions_due_for_notification(
            days_before=days_before, 
            target_time=target_time
        )
        
        if not subscriptions_to_notify:
            message = "No subscriptions found with matching reminders"
            if target_time:
                message += f" at {target_time.strftime('%I:%M %p')}"
            self.stdout.write(self.style.SUCCESS(message))
            return
        
        sent_count = 0
        skipped_count = 0
        error_count = 0
        
        for subscription, offset in subscriptions_to_notify:
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
                    if not NotificationService.send_renewal_reminder(subscription, days_before=offset):
                        skipped_count += 1
                        continue
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
        self.stdout.write("Summary for scheduled reminders:")

        if target_time:
            self.stdout.write(f"Time filter: {target_time.strftime('%I:%M %p')}")
        self.stdout.write(f"  Sent: {sent_count}")
        self.stdout.write(f"  Skipped: {skipped_count}")
        self.stdout.write(f"  Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("This was a dry run - no emails were actually sent"))
        if error_count:
            raise CommandError(f"{error_count} renewal reminder(s) failed.")
