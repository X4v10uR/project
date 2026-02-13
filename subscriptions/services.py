from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from datetime import date, timedelta, datetime
from .models import Subscription, NotificationLog
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for handling subscription notifications"""
    
    @staticmethod
    def send_renewal_reminder(subscription, days_before=3):
        """Send a renewal reminder email for a subscription"""
        try:
            user = subscription.user
            
            # Check if reminders are enabled for this subscription
            if not subscription.reminders_enabled:
                logger.info(f"Reminders disabled for {subscription.service_name} (User: {user.email})")
                return False

            # Check if notification already sent for this renewal and offset
            if NotificationLog.objects.filter(
                subscription=subscription,
                notification_type='renewal_reminder',
                renewal_date=subscription.renewal_date,
                days_before=days_before
            ).exists():
                logger.info(f"Notification already sent for {subscription.service_name} at {days_before} days offset to {user.email}")
                return False
            
            # Prepare email context
            context = {
                'user': user,
                'subscription': subscription,
                'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000'),
            }
            
            # Render email templates
            subject = render_to_string('emails/renewal_reminder_subject.txt', context).strip()
            text_content = render_to_string('emails/renewal_reminder.txt', context)
            html_content = render_to_string('emails/renewal_reminder.html', context)
            
            # Send email
            send_mail(
                subject=subject,
                message=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_content,
                fail_silently=False,
            )
            
            # Log the notification
            NotificationLog.objects.create(
                subscription=subscription,
                notification_type='renewal_reminder',
                renewal_date=subscription.renewal_date,
                days_before=days_before
            )
            
            logger.info(f"Renewal reminder sent for {subscription.service_name} to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send renewal reminder: {str(e)}", exc_info=True)
            raise
    
    @staticmethod
    def get_subscriptions_due_for_notification(target_time=None, days_before=None):
        """Get subscriptions and their offsets that need renewal notifications today"""
        today = date.today()
        
        # Subscriptions with reminders enabled
        active_subs = Subscription.objects.filter(
            status='active',
            reminders_enabled=True
        ).prefetch_related('offsets')
        
        due_notifications = []

        for sub in active_subs:
            if not sub.renewal_date:
                continue

            # Calculate days until renewal
            days_until = (sub.renewal_date - today).days

            custom_offsets = {offset.days_before for offset in sub.offsets.all()}
            matched_offset = None

            if custom_offsets:
                if days_until in custom_offsets:
                    matched_offset = days_until
            elif days_until == 3:
                matched_offset = 3

            if matched_offset is None:
                continue

            if days_before is not None and matched_offset != days_before:
                continue

            due_notifications.append((sub, matched_offset))

        # Filter by time if provided
        if target_time:
            time_window_start = (datetime.combine(date.today(), target_time) - timedelta(hours=1)).time()
            time_window_end = (datetime.combine(date.today(), target_time) + timedelta(hours=1)).time()
            
            due_notifications = [
                (sub, offset) for sub, offset in due_notifications
                if sub.renewal_time is None or (sub.renewal_time >= time_window_start and sub.renewal_time <= time_window_end)
            ]
        
        return due_notifications
    
    @staticmethod
    def send_batch_notifications(target_time=None, dry_run=False):
        """Send notifications for all subscriptions due today based on their offsets"""
        notifications_to_send = NotificationService.get_subscriptions_due_for_notification(target_time)
        
        results = {
            'sent': 0,
            'skipped': 0,
            'errors': 0,
            'total': len(notifications_to_send)
        }
        
        for subscription, days_before in notifications_to_send:
            try:
                if dry_run:
                    results['sent'] += 1
                    continue

                was_sent = NotificationService.send_renewal_reminder(subscription, days_before)
                if was_sent:
                    results['sent'] += 1
                else:
                    results['skipped'] += 1
            except Exception as e:
                results['errors'] += 1
                logger.error(f"Failed to send notification for {subscription.id} at {days_before} offset: {str(e)}")
        
        return results
