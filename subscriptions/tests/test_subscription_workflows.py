from datetime import date, time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Team, TeamMembership
from subscriptions.models import (
    InAppNotification,
    NotificationLog,
    ReminderOffset,
    Subscription,
    SubscriptionParticipant,
    Transaction,
)
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
                'display_color': '#F9F871',
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
        self.assertEqual(subscription.display_color, '#F9F871')

    def test_create_active_subscription_records_initial_transaction(self):
        response = self.client.post(
            reverse('subscriptions:create'),
            data={
                'service_name': 'Notion',
                'display_color': '#AFC0DE',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '12.50',
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
            },
        )

        self.assertEqual(response.status_code, 302)
        subscription = Subscription.objects.get(user=self.user, service_name='Notion')
        transaction = Transaction.objects.get(subscription=subscription)
        self.assertEqual(transaction.source, Transaction.SOURCE_RENEWAL)
        self.assertEqual(transaction.amount, Decimal('12.50'))
        self.assertEqual(transaction.charged_for_date, date.today())

    def test_update_replaces_existing_reminder_offsets(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Disney+',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('12.99'),
            start_date=date.today(),
            status='active',
        )
        ReminderOffset.objects.create(subscription=subscription, days_before=3)
        ReminderOffset.objects.create(subscription=subscription, days_before=7)

        response = self.client.post(
            reverse('subscriptions:update', args=[subscription.pk]),
            data={
                'service_name': 'Disney+',
                'category': 'Streaming',
                'billing_cycle': 'monthly',
                'cost': '12.99',
                'currency': 'USD',
                'start_date': date.today().isoformat(),
                'renewal_time': '15:00',
                'status': 'active',
                'reminders_enabled': 'on',
                'card': '',
                'notes': '',
                'is_shared': 'False',
                'split_type': 'equal',
                'participant_name': [],
                'participant_share': [],
                'account_email': '',
                'account_password': '',
                'reminder_offsets': ['1', '5'],
            },
        )

        self.assertEqual(response.status_code, 302)
        offsets = sorted(subscription.offsets.values_list('days_before', flat=True))
        self.assertEqual(offsets, [1, 5])

    def test_update_with_no_offsets_clears_existing_custom_offsets(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Canva',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=date.today(),
            status='active',
        )
        ReminderOffset.objects.create(subscription=subscription, days_before=3)

        response = self.client.post(
            reverse('subscriptions:update', args=[subscription.pk]),
            data={
                'service_name': 'Canva',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '9.99',
                'currency': 'USD',
                'start_date': date.today().isoformat(),
                'renewal_time': '15:00',
                'status': 'active',
                'reminders_enabled': 'on',
                'card': '',
                'notes': '',
                'is_shared': 'False',
                'split_type': 'equal',
                'participant_name': [],
                'participant_share': [],
                'account_email': '',
                'account_password': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(subscription.offsets.exists())

    def test_update_persists_selected_display_color(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Figma',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('12.00'),
            start_date=date.today(),
            status='active',
        )

        response = self.client.post(
            reverse('subscriptions:update', args=[subscription.pk]),
            data={
                'service_name': 'Figma',
                'display_color': '#AFC0DE',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '12.00',
                'currency': 'USD',
                'start_date': date.today().isoformat(),
                'renewal_time': '15:00',
                'status': 'active',
                'reminders_enabled': 'on',
                'card': '',
                'notes': '',
                'is_shared': 'False',
                'split_type': 'equal',
                'participant_name': [],
                'participant_share': [],
                'account_email': '',
                'account_password': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        subscription.refresh_from_db()
        self.assertEqual(subscription.display_color, '#AFC0DE')


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

    def test_midnight_time_window_matches_due_subscription(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Midnight Service',
            category='Utilities',
            billing_cycle='weekly',
            cost=Decimal('4.99'),
            start_date=date.today() - timedelta(days=4),  # renews in 3 days
            renewal_time=time(0, 15),
            status='active',
            reminders_enabled=True,
        )

        due = NotificationService.get_subscriptions_due_for_notification(
            target_time=time(0, 30),
            days_before=3,
        )

        self.assertTrue(
            any(sub.pk == subscription.pk and offset == 3 for sub, offset in due),
            'Expected midnight renewal_time to match the +/-1 hour window around 00:30.',
        )

    def test_send_reminder_returns_false_when_duplicate_log_exists(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Duplicate Reservation Service',
            category='Streaming',
            billing_cycle='weekly',
            cost=Decimal('4.99'),
            start_date=date.today() - timedelta(days=4),
            status='active',
            reminders_enabled=True,
        )

        NotificationLog.objects.create(
            subscription=subscription,
            notification_type='renewal_reminder',
            renewal_date=subscription.renewal_date,
            days_before=3,
        )

        with mock.patch('subscriptions.services.send_mail') as mocked_send_mail:
            was_sent = NotificationService.send_renewal_reminder(subscription, days_before=3)

        self.assertFalse(was_sent)
        mocked_send_mail.assert_not_called()

    def test_send_reminder_releases_reservation_on_email_failure(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Reservation Cleanup Service',
            category='Streaming',
            billing_cycle='weekly',
            cost=Decimal('4.99'),
            start_date=date.today() - timedelta(days=4),
            status='active',
            reminders_enabled=True,
        )

        with mock.patch(
            'subscriptions.services.send_mail',
            side_effect=RuntimeError('SMTP unavailable'),
        ):
            with self.assertRaises(RuntimeError):
                NotificationService.send_renewal_reminder(subscription, days_before=3)

        self.assertFalse(
            NotificationLog.objects.filter(
                subscription=subscription,
                notification_type='renewal_reminder',
                renewal_date=subscription.renewal_date,
                days_before=3,
            ).exists()
        )

    def test_team_reminder_uses_single_email_send_for_all_members(self):
        team_owner = User.objects.create_user(email='owner-team-notify@example.com', password='password')
        team_member = User.objects.create_user(email='member-team-notify@example.com', password='password')

        team = Team.objects.create(name='Notify Team', created_by=team_owner)
        TeamMembership.objects.create(team=team, user=team_owner, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=team, user=team_member, role=TeamMembership.ROLE_MEMBER)

        subscription = Subscription.objects.create(
            user=team_owner,
            team=team,
            service_name='Team Reminder Service',
            category='Software',
            billing_cycle='weekly',
            cost=Decimal('6.99'),
            start_date=date.today() - timedelta(days=4),
            status='active',
            reminders_enabled=True,
        )

        with mock.patch('subscriptions.services.send_mail', return_value=1) as mocked_send_mail:
            was_sent = NotificationService.send_renewal_reminder(subscription, days_before=3)

        self.assertTrue(was_sent)
        self.assertEqual(mocked_send_mail.call_count, 1)
        kwargs = mocked_send_mail.call_args.kwargs
        self.assertCountEqual(
            kwargs['recipient_list'],
            [team_owner.email, team_member.email],
        )
        self.assertEqual(
            InAppNotification.objects.filter(
                subscription=subscription,
                event_type='renewal.reminder',
            ).count(),
            2,
        )
