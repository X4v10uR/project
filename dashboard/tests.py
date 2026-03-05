import json
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from dashboard.services import _days_left_text
from subscriptions.models import InAppNotification, Subscription
from dashboard.models import BalanceAdjustment

User = get_user_model()


class DashboardViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='dash@example.com', password='password')
        self.client.force_login(self.user)

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_renders_with_context(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/dashboard.html')
        for key in ['total_active', 'total_paused', 'total_cancelled', 'total_shared',
                     'monthly_spend', 'yearly_spend', 'avg_monthly_spend',
                     'upcoming_renewals', 'status_dist',
                     'balance_trend_points', 'balance_trend_start_label',
                     'balance_trend_end_label', 'balance_trend_has_activity',
                     'balance_display', 'balance_base_display', 'balance_adjustment_display']:
            self.assertIn(key, response.context)

    def test_dashboard_fixed_slot_sections_are_padded(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(len(response.context['upcoming_bills']), 3)
        self.assertEqual(len(response.context['subscriptions_panel']), 3)
        self.assertEqual(len(response.context['active_subscriptions_panel']), 2)
        self.assertEqual(len(response.context['recent_transactions']), 2)

    def test_bell_url_points_to_notifications_page(self):
        response = self.client.get(reverse('dashboard:home'))
        bell_url = response.context['bell_url']
        parsed = urlparse(bell_url)
        self.assertEqual(parsed.path, reverse('dashboard:notifications_page'))

    def test_shared_count_is_correct(self):
        Subscription.objects.create(
            user=self.user, service_name='Solo', category='Util',
            billing_cycle='monthly', cost=Decimal('5.00'),
            start_date=date.today(), status='active', is_shared=False,
        )
        Subscription.objects.create(
            user=self.user, service_name='Family', category='Streaming',
            billing_cycle='monthly', cost=Decimal('15.00'),
            user_cost=Decimal('5.00'),
            start_date=date.today(), status='active', is_shared=True,
        )
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['total_shared'], 1)
        self.assertEqual(response.context['total_active'], 2)

    def test_monthly_spend_display_handles_multiple_currencies(self):
        Subscription.objects.create(
            user=self.user,
            service_name='US Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('5.00'),
            currency='USD',
            start_date=date.today(),
            status='active',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='EU Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('7.00'),
            currency='EUR',
            start_date=date.today(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'))
        display = response.context['monthly_spend_display']

        self.assertIn('$5.00', display)
        self.assertIn('EUR 7.00', display)
        self.assertEqual(response.context['monthly_spend'], Decimal('5.00'))
        self.assertEqual(response.context['yearly_spend'], Decimal('60.00'))
        self.assertEqual(response.context['avg_monthly_spend'], Decimal('5.00'))

    def test_weekly_subscription_uses_52_over_12_monthly_equivalent(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Weekly Service',
            category='Software',
            billing_cycle='weekly',
            cost=Decimal('12.00'),
            currency='USD',
            start_date=date.today(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['monthly_spend'], Decimal('52.00'))
        self.assertEqual(
            response.context['monthly_spend_by_currency']['USD'],
            Decimal('52.00'),
        )

    def test_balance_trend_points_cover_30_days(self):
        response = self.client.get(reverse('dashboard:home'))
        points = response.context['balance_trend_points']

        self.assertEqual(len(points), 30)
        self.assertEqual(
            response.context['balance_trend_start_label'],
            (date.today() - timedelta(days=29)).strftime('%b %d'),
        )
        self.assertEqual(
            response.context['balance_trend_end_label'],
            date.today().strftime('%b %d'),
        )

    def test_balance_trend_uses_recent_transactions(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Spotify',
            category='Music',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=date.today(),
            status='active',
        )

        transaction_date = date.today() - timedelta(days=2)
        subscription.transactions.create(
            user=self.user,
            service_name_snapshot='Spotify',
            amount=Decimal('9.99'),
            currency='USD',
            charged_for_date=transaction_date,
        )

        response = self.client.get(reverse('dashboard:home'))
        points = response.context['balance_trend_points']

        self.assertEqual(len(points), 30)
        self.assertTrue(response.context['balance_trend_has_activity'])
        self.assertAlmostEqual(points[-3], 9.99, places=2)

    def test_balance_display_includes_manual_adjustment(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Streaming Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('20.00'),
            currency='USD',
            start_date=date.today(),
            status='active',
        )
        BalanceAdjustment.objects.create(user=self.user, amount=Decimal('5.25'))

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['balance_display'], '$25.25')
        self.assertEqual(response.context['balance_base_display'], '$20.00')
        self.assertEqual(response.context['balance_adjustment_display'], '+$5.25')

    def test_adjust_balance_endpoint_sets_target_balance(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Cloud Service',
            category='Cloud',
            billing_cycle='monthly',
            cost=Decimal('40.00'),
            currency='USD',
            start_date=date.today(),
            status='active',
        )

        response = self.client.post(
            reverse('dashboard:adjust_balance'),
            data=json.dumps({'target_balance': '55.50'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['balance_display'], '$55.50')
        self.assertEqual(payload['balance_base_display'], '$40.00')
        self.assertEqual(payload['balance_adjustment_display'], '+$15.50')

        adjustment = BalanceAdjustment.objects.get(user=self.user)
        self.assertEqual(adjustment.amount, Decimal('15.50'))

    def test_adjust_balance_endpoint_rejects_invalid_amount(self):
        response = self.client.post(
            reverse('dashboard:adjust_balance'),
            data=json.dumps({'target_balance': 'not-a-number'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['ok'])

    def test_dashboard_does_not_mutate_stale_renewal_dates(self):
        today = date.today()
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Stale Renewal Service',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('12.00'),
            start_date=today,
            status='active',
        )

        Subscription.objects.filter(pk=subscription.pk).update(
            renewal_date=today - timedelta(days=10)
        )

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.renewal_date, today - timedelta(days=10))
        self.assertTrue(
            any(sub.pk == subscription.pk for sub in response.context['upcoming_renewals'])
        )

    def test_dashboard_home_does_not_create_balance_adjustment_row(self):
        self.assertFalse(BalanceAdjustment.objects.filter(user=self.user).exists())

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)

        self.assertFalse(BalanceAdjustment.objects.filter(user=self.user).exists())

    def test_days_left_text_handles_overdue_dates(self):
        today = date.today()
        self.assertEqual(_days_left_text(today - timedelta(days=1), today), '1 day overdue')
        self.assertEqual(_days_left_text(today - timedelta(days=3), today), '3 days overdue')

    def test_service_color_is_consistent_across_sections(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Spotify',
            category='Music',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=date.today(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'))
        upcoming = next(
            item for item in response.context['upcoming_bills']
            if not item['is_placeholder'] and item['service_name'] == 'Spotify'
        )
        subscriptions_item = next(
            item for item in response.context['subscriptions_panel']
            if not item['is_placeholder'] and item['title'] == 'Spotify'
        )
        active_item = next(
            item for item in response.context['active_subscriptions_panel']
            if not item['is_placeholder'] and item['title'] == 'Spotify'
        )

        self.assertEqual(upcoming['bg_style'], subscriptions_item['bg_style'])
        self.assertEqual(subscriptions_item['bg_style'], active_item['bg_style'])

    def test_visible_subscriptions_use_distinct_colors(self):
        for service_name in ['Spotify', 'Netflix', 'Apple TV']:
            Subscription.objects.create(
                user=self.user,
                service_name=service_name,
                category='Streaming',
                billing_cycle='monthly',
                cost=Decimal('10.00'),
                start_date=date.today(),
                status='active',
            )

        response = self.client.get(reverse('dashboard:home'))
        visible_items = [
            item for item in response.context['subscriptions_panel']
            if not item['is_placeholder']
        ]
        colors = [item['bg_style'] for item in visible_items]

        self.assertEqual(len(colors), len(set(colors)))


class LandingPageTest(TestCase):
    def test_authenticated_user_redirected_to_dashboard(self):
        user = User.objects.create_user(email='land@example.com', password='password')
        self.client.force_login(user)
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_user_sees_landing(self):
        response = self.client.get('/')
        # Landing page should be accessible (200) or redirect
        self.assertIn(response.status_code, [200, 302])


class NotificationApiTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='notify-api@example.com', password='password')
        self.client.force_login(self.user)

    def test_unread_count_and_mark_read(self):
        notification = InAppNotification.objects.create(
            recipient=self.user,
            event_type='subscription.created',
            title='New subscription',
            body='Netflix added',
        )

        count_response = self.client.get(reverse('dashboard:notifications_unread_count_api'))
        self.assertEqual(count_response.status_code, 200)
        self.assertEqual(count_response.json()['unread_count'], 1)

        mark_read_response = self.client.post(reverse('dashboard:notification_mark_read_api', args=[notification.pk]))
        self.assertEqual(mark_read_response.status_code, 200)
        self.assertEqual(mark_read_response.json()['unread_count'], 0)

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_read_marks_everything(self):
        InAppNotification.objects.create(
            recipient=self.user,
            event_type='team.invite.sent',
            title='Invite sent',
        )
        InAppNotification.objects.create(
            recipient=self.user,
            event_type='subscription.updated',
            title='Subscription updated',
        )

        response = self.client.post(reverse('dashboard:notifications_mark_all_read_api'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['unread_count'], 0)
        self.assertEqual(InAppNotification.objects.filter(recipient=self.user, is_read=False).count(), 0)
        self.assertEqual(
            InAppNotification.objects.filter(recipient=self.user, read_at__isnull=False).count(),
            2,
        )
