from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from subscriptions.models import NotificationLog, Subscription, SubscriptionParticipant
from subscriptions.services import NotificationService

User = get_user_model()


class SubscriptionWorkflowSafetyTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='owner@example.com', password='password')
        self.client.force_login(self.user)

    def test_invalid_custom_split_does_not_delete_existing_participants(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Netflix',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            user_cost=Decimal('5.00'),
            is_shared=True,
            split_type='equal',
            start_date=date.today(),
            status='active',
        )
        SubscriptionParticipant.objects.create(
            subscription=subscription,
            name='Alice',
            share_amount=Decimal('5.00'),
        )

        response = self.client.post(
            reverse('subscriptions:update', args=[subscription.pk]),
            data={
                'service_name': 'Netflix',
                'category': 'Streaming',
                'billing_cycle': 'monthly',
                'cost': '10.00',
                'currency': 'USD',
                'start_date': date.today().isoformat(),
                'renewal_time': '15:00',
                'status': 'active',
                'reminders_enabled': 'on',
                'notes': '',
                'card': '',
                'is_shared': 'True',
                'split_type': 'custom',
                'participant_name': ['Alice'],
                'participant_share': ['20.00'],
                'account_email': '',
                'account_password': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        subscription.refresh_from_db()
        participants = list(subscription.participants.order_by('id'))
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants[0].name, 'Alice')
        self.assertEqual(participants[0].share_amount, Decimal('5.00'))

    def test_create_deduplicates_reminder_offsets(self):
        response = self.client.post(
            reverse('subscriptions:create'),
            data={
                'service_name': 'Hulu',
                'category': 'Streaming',
                'billing_cycle': 'monthly',
                'cost': '11.99',
                'currency': 'USD',
                'start_date': date.today().isoformat(),
                'renewal_time': '15:00',
                'status': 'active',
                'reminders_enabled': 'on',
                'notes': '',
                'card': '',
                'is_shared': 'False',
                'split_type': 'equal',
                'participant_name': [],
                'participant_share': [],
                'account_email': '',
                'account_password': '',
                'reminder_offsets': ['3', '3', '7', 'invalid', '45'],
            },
        )

        self.assertEqual(response.status_code, 302)

        subscription = Subscription.objects.get(user=self.user, service_name='Hulu')
        offsets = sorted(subscription.offsets.values_list('days_before', flat=True))
        self.assertEqual(offsets, [3, 7])


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotificationServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='notify@example.com', password='password')

    def test_send_batch_notifications_counts_skipped(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Prime Video',
            category='Streaming',
            billing_cycle='weekly',
            cost=Decimal('9.99'),
            start_date=date.today() - timedelta(days=4),  # renews in 3 days
            status='active',
            reminders_enabled=True,
        )

        NotificationLog.objects.create(
            subscription=subscription,
            notification_type='renewal_reminder',
            renewal_date=subscription.renewal_date,
            days_before=3,
        )

        results = NotificationService.send_batch_notifications()

        self.assertEqual(results['total'], 1)
        self.assertEqual(results['sent'], 0)
        self.assertEqual(results['skipped'], 1)
        self.assertEqual(results['errors'], 0)
