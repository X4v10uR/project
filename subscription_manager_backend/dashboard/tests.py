import json
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse
from unittest.mock import patch

from django.contrib.auth import get_user_model
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.db import connection, transaction
from django.test import TestCase, Client, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccountSecurity, Team, TeamMembership
from dashboard.services import _days_left_text, build_dashboard_view_model
from finance.models import Activity, NotificationDelivery
from subscriptions.models import InAppNotification, Subscription
from subscriptions.notifications import create_notification
from dashboard.models import BalanceAdjustment

User = get_user_model()


class NotificationDeliveryTest(TestCase):
    @patch('subscriptions.notifications._send_notification_email')
    @patch('subscriptions.notifications.push_created')
    def test_notification_delivery_waits_for_commit(self, push, email):
        user = User.objects.create_user(email='delivery@example.com')
        with self.captureOnCommitCallbacks(execute=True):
            notification = create_notification(
                recipient=user, event_type='test.created', title='Committed event', send_email_alert=True,
            )
            push.assert_not_called()
            email.assert_not_called()
        push.assert_called_once_with(notification)
        email.assert_called_once_with(notification)

    @patch('subscriptions.notifications._send_notification_email')
    @patch('subscriptions.notifications.push_created')
    def test_rolled_back_notification_is_never_delivered(self, push, email):
        user = User.objects.create_user(email='rollback@example.com')
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError), transaction.atomic():
                create_notification(
                    recipient=user, event_type='test.created', title='Rolled back event', send_email_alert=True,
                )
                raise ValueError('Cancel the operation')
        self.assertFalse(InAppNotification.objects.filter(recipient=user).exists())
        push.assert_not_called()
        email.assert_not_called()


@override_settings(
    ALLOWED_HOSTS=['testserver'],
    CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}},
)
class NotificationWebSocketTest(TransactionTestCase):
    def test_socket_requires_current_mfa_revision_on_connect_and_delivery(self):
        from subly.asgi import application

        user = User.objects.create_user(email='socket-mfa@example.com')
        security = AccountSecurity.objects.create(user=user, enabled=True, revision='current')
        self.client.force_login(user)
        session = self.client.session
        session['mfa_revision'] = security.revision
        session.save()
        headers = [(b'origin', b'http://testserver'),
                   (b'cookie', f'{settings.SESSION_COOKIE_NAME}={session.session_key}'.encode())]

        async def scenario():
            connection = WebsocketCommunicator(application, '/ws/notifications/', headers=headers)
            self.assertTrue((await connection.connect())[0])
            try:
                await AccountSecurity.objects.filter(pk=security.pk).aupdate(revision='updated')
                await get_channel_layer().group_send(f'notifications_user_{user.pk}', {'type': 'notification.bulk_read'})
                self.assertEqual(await connection.receive_output(), {'type': 'websocket.close', 'code': 4401})
            finally:
                await connection.disconnect()
            new_connection = WebsocketCommunicator(application, '/ws/notifications/', headers=headers)
            try:
                self.assertEqual(await new_connection.connect(), (False, 4401))
            finally:
                await new_connection.disconnect()

        async_to_sync(scenario)()

    def test_logged_out_session_cannot_receive_further_events(self):
        from subly.asgi import application

        user = User.objects.create_user(email='socket@example.com')
        self.client.force_login(user)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value

        async def scenario():
            connection = WebsocketCommunicator(
                application, '/ws/notifications/',
                headers=[
                    (b'origin', b'http://testserver'),
                    (b'cookie', f'{settings.SESSION_COOKIE_NAME}={cookie}'.encode()),
                ],
            )
            connected, _ = await connection.connect()
            self.assertTrue(connected)
            try:
                layer = get_channel_layer()
                group = f'notifications_user_{user.pk}'
                event = {'type': 'notification.bulk_read', 'unread_count': 0}
                await layer.group_send(group, event)
                self.assertEqual(await connection.receive_json_from(), event)

                await database_sync_to_async(self.client.logout)()
                await layer.group_send(group, event)
                self.assertEqual(
                    await connection.receive_output(), {'type': 'websocket.close', 'code': 4401}
                )
            finally:
                await connection.disconnect()

        async_to_sync(scenario)()


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

    def test_balance_stats_page_renders_with_context(self):
        response = self.client.get(reverse('dashboard:balance_stats'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/balance_stats.html')
        for key in [
            'stats_upcoming_bill_balance_display',
            'stats_total_subscriptions_balance_display',
            'stats_total_active',
            'stats_total_paused',
            'stats_total_cancelled',
        ]:
            self.assertIn(key, response.context)

    def test_balance_stats_global_alias_route_resolves(self):
        response = self.client.get(reverse('balance_stats'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/balance_stats.html')

    def test_dashboard_fixed_slot_sections_are_padded_when_empty(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(len(response.context['upcoming_bills']), 3)
        self.assertEqual(len(response.context['subscriptions_panel']), 3)
        self.assertEqual(len(response.context['active_subscriptions_panel']), 2)
        self.assertEqual(len(response.context['recent_transactions']), 0)

    def test_active_subscriptions_panel_includes_all_active_subscriptions(self):
        for service_name in ['Spotify', 'Netflix', 'Apple TV']:
            Subscription.objects.create(
                user=self.user,
                service_name=service_name,
                category='Streaming',
                billing_cycle='monthly',
                cost=Decimal('10.00'),
                start_date=timezone.localdate(),
                status='active',
            )

        response = self.client.get(reverse('dashboard:home'))
        visible_titles = [
            item['title']
            for item in response.context['active_subscriptions_panel']
            if not item['is_placeholder']
        ]

        self.assertEqual(len(visible_titles), 3)
        self.assertEqual(sorted(visible_titles), ['Apple TV', 'Netflix', 'Spotify'])

    def test_upcoming_bills_include_all_upcoming_subscriptions(self):
        for service_name in ['Spotify', 'Netflix', 'Apple TV', 'Paramount+']:
            Subscription.objects.create(
                user=self.user,
                service_name=service_name,
                category='Streaming',
                billing_cycle='monthly',
                cost=Decimal('10.00'),
                start_date=timezone.localdate() + timedelta(days=5),
                status='active',
            )

        response = self.client.get(reverse('dashboard:home'))
        visible_names = [
            item['service_name']
            for item in response.context['upcoming_bills']
            if not item['is_placeholder']
        ]

        self.assertEqual(len(visible_names), 4)
        self.assertEqual(sorted(visible_names), ['Apple TV', 'Netflix', 'Paramount+', 'Spotify'])

    def test_bell_url_points_to_notifications_page(self):
        response = self.client.get(reverse('dashboard:home'))
        bell_url = response.context['bell_url']
        parsed = urlparse(bell_url)
        self.assertEqual(parsed.path, reverse('dashboard:notifications_page'))

    def test_shared_count_is_correct(self):
        Subscription.objects.create(
            user=self.user, service_name='Solo', category='Util',
            billing_cycle='monthly', cost=Decimal('5.00'),
            start_date=timezone.localdate(), status='active', is_shared=False,
        )
        Subscription.objects.create(
            user=self.user, service_name='Family', category='Streaming',
            billing_cycle='monthly', cost=Decimal('15.00'),
            user_cost=Decimal('5.00'),
            start_date=timezone.localdate(), status='active', is_shared=True,
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
            start_date=timezone.localdate(),
            status='active',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='EU Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('7.00'),
            currency='EUR',
            start_date=timezone.localdate(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'))
        display = response.context['monthly_spend_display']

        self.assertIn('$5.00', display)
        self.assertIn('EUR 7.00', display)
        self.assertEqual(response.context['monthly_spend'], Decimal('5.00'))
        self.assertEqual(response.context['yearly_spend'], Decimal('60.00'))
        self.assertEqual(response.context['avg_monthly_spend'], Decimal('5.00'))

    def test_balance_stats_include_upcoming_total_and_status_totals(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Active Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            currency='USD',
            start_date=timezone.localdate() + timedelta(days=5),
            status='active',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='Paused Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('20.00'),
            currency='USD',
            start_date=timezone.localdate() + timedelta(days=5),
            status='paused',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='Cancelled Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('30.00'),
            currency='USD',
            start_date=timezone.localdate() + timedelta(days=5),
            status='cancelled',
        )

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['stats_upcoming_bill_balance_display'], '$10.00')
        self.assertEqual(response.context['stats_total_subscriptions_balance_display'], '$60.00')
        self.assertEqual(response.context['stats_total_active'], '$10.00')
        self.assertEqual(response.context['stats_total_paused'], '$20.00')
        self.assertEqual(response.context['stats_total_cancelled'], '$30.00')

    def test_weekly_subscription_uses_52_over_12_monthly_equivalent(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Weekly Service',
            category='Software',
            billing_cycle='weekly',
            cost=Decimal('12.00'),
            currency='USD',
            start_date=timezone.localdate(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.context['monthly_spend'], Decimal('52.00'))
        self.assertEqual(
            response.context['monthly_spend_by_currency']['USD'],
            Decimal('52.00'),
        )

    def test_resumed_plan_counts_toward_spend_balance_and_budget(self):
        today = timezone.localdate()
        plan = Subscription.objects.create(
            user=self.user, service_name='Resumed', billing_cycle='monthly', currency='EUR',
            cost=Decimal('12'), start_date=today, status='paused',
            pause_from=today - timedelta(days=7), resume_on=today,
        )
        Subscription.objects.create(
            user=self.user, service_name='On hold', billing_cycle='monthly', currency='EUR',
            cost=Decimal('8'), start_date=today, status='active', pause_from=today,
        )
        self.client.put(reverse('dashboard_api:budget'), {'currency': 'EUR', 'monthly_limit': '10'},
                        content_type='application/json')
        response = self.client.post(reverse('dashboard_api:adjust_balance'),
                                    {'currency': 'EUR', 'target_balance': '20'}, content_type='application/json')
        self.assertEqual(response.json()['balance_adjustment_display'], '+EUR 8.00')
        data = self.client.get(reverse('dashboard_api:home'), {'currency': 'EUR'}).json()
        self.assertEqual(data['monthly_spend_by_currency'], {'EUR': '12.00'})
        self.assertEqual((data['monthly_spend'], data['yearly_spend'], data['avg_monthly_spend']),
                         ('12.00', '144.00', '12.00'))
        self.assertEqual([row['id'] for row in data['active_subscriptions_panel']], [plan.pk])
        self.assertEqual(data['stats_total_paused'], 'EUR 8.00')
        self.assertEqual(data['balance_display'], 'EUR 20.00')
        self.assertTrue(data['over_budget'])
        self.assertTrue(InAppNotification.objects.filter(recipient=self.user, event_type='budget.exceeded').exists())

    def test_next_bill_uses_first_charge_after_pause(self):
        first = timezone.localdate() + timedelta(days=1)
        resume = first + timedelta(weeks=1)
        Subscription.objects.create(
            user=self.user, service_name='Weekly', billing_cycle='weekly', cost=Decimal('10'),
            start_date=first, pause_from=first, resume_on=resume,
        )
        data = self.client.get(reverse('dashboard_api:home')).json()
        self.assertEqual(data['upcoming_bills'][0]['date'], resume.isoformat())
        self.assertEqual(data['balance_chip_date'], resume.strftime('%m/%d'))

    def test_dashboard_uses_its_reporting_date_for_prices(self):
        today = timezone.localdate()
        after_intro = today + timedelta(days=5)
        Subscription.objects.create(
            user=self.user, service_name='Intro', billing_cycle='monthly', cost=Decimal('15'),
            start_date=today, introductory_cost=Decimal('5'), introductory_until=after_intro,
        )
        data = build_dashboard_view_model(self.user, today=after_intro)
        self.assertEqual(data['monthly_spend'], Decimal('15'))
        self.assertEqual(data['active_subscriptions_panel'][0]['amount'], '$15.00')
        self.assertEqual(data['subscriptions_panel'][0]['subtitle'], '$15.00/monthly')

    def test_forecast_reserves_custom_color_of_a_paused_plan_due_to_resume(self):
        today = timezone.localdate()
        fields = {'user': self.user, 'billing_cycle': 'weekly', 'cost': Decimal('5'), 'start_date': today}
        Subscription.objects.create(service_name='Spotify', **fields)
        Subscription.objects.create(service_name='Studio', display_color='#7BCFC0', status='paused',
                                    resume_on=today + timedelta(weeks=1), **fields)
        data = self.client.get(reverse('dashboard_api:home')).json()
        colors = {row['service_name']: row['bg_style'] for row in data['upcoming_bills']}
        self.assertEqual(colors['Studio'], 'background-color: #7BCFC0;')
        self.assertNotEqual(colors['Spotify'].upper(), colors['Studio'].upper())

    def test_balance_trend_points_cover_30_days(self):
        response = self.client.get(reverse('dashboard:home'))
        points = response.context['balance_trend_points']

        self.assertEqual(len(points), 30)
        self.assertEqual(
            response.context['balance_trend_start_label'],
            (timezone.localdate() - timedelta(days=29)).strftime('%b %d'),
        )
        self.assertEqual(
            response.context['balance_trend_end_label'],
            timezone.localdate().strftime('%b %d'),
        )

    def test_balance_trend_uses_recent_transactions(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Spotify',
            category='Music',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=timezone.localdate(),
            status='active',
        )

        transaction_date = timezone.localdate() - timedelta(days=2)
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
            start_date=timezone.localdate(),
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
            start_date=timezone.localdate(),
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

    def test_balance_api_validates_scope_before_updating(self):
        url = reverse('dashboard_api:adjust_balance')
        for path, payload in (
            (url, {'scope': 'team', 'target_balance': '50'}),
            (url + '?scope=unknown', {'target_balance': '50'}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, payload, content_type='application/json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('scope', response.json())
        self.assertFalse(BalanceAdjustment.objects.filter(user=self.user).exists())

        response = self.client.post(url + '?scope=TEAMS', {'target_balance': '50'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dashboard_scope'], 'teams')
        self.assertEqual(BalanceAdjustment.objects.get(user=self.user).scope, 'teams')

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

    def test_legacy_balance_rejects_unknown_scope_without_changing_personal_balance(self):
        url = reverse('dashboard:adjust_balance')
        for scope in ('team', False, []):
            with self.subTest(scope=scope):
                response = self.client.post(url, {'scope': scope, 'target_balance': '55'}, content_type='application/json')
                self.assertEqual(response.status_code, 400)
        self.assertFalse(BalanceAdjustment.objects.filter(user=self.user).exists())

    def test_retrying_payment_and_reimbursement_records_each_change_once(self):
        sub = Subscription.objects.create(user=self.user, service_name='Shared studio', billing_cycle='monthly',
                                          cost=Decimal('16'), start_date=timezone.localdate())
        charge = sub.transactions.create(user=self.user, service_name_snapshot=sub.service_name,
                                         charged_for_date=sub.start_date, amount=Decimal('8'))
        share = charge.shares.create(name='Colleague', amount=Decimal('8'))
        for url, args, payload, action in (
            ('dashboard_api:payment', [charge.pk], {'payment_status': 'paid'}, 'payment.status.changed'),
            ('dashboard_api:share', [charge.pk, share.pk], {'reimbursed': True}, 'share.reimbursement.changed'),
        ):
            with self.subTest(action=action):
                for _ in range(2):
                    result = self.client.patch(reverse(url, args=args), payload, content_type='application/json')
                    self.assertEqual(result.status_code, 200)
                self.assertEqual(Activity.objects.filter(subscription=sub, action=action).count(), 1)

    def test_history_loads_repayment_flags_without_a_query_per_share(self):
        sub = Subscription.objects.create(user=self.user, service_name='Shared studio', billing_cycle='monthly',
                                          cost=Decimal('16'), start_date=timezone.localdate())
        charge = sub.transactions.create(user=self.user, service_name_snapshot=sub.service_name,
                                         charged_for_date=sub.start_date, amount=Decimal('8'))
        share = charge.shares.create(name='A', amount=Decimal('4'))
        share.repayments.create(amount=Decimal('2'), recorded_by=self.user)
        url = reverse('dashboard_api:history')
        with CaptureQueriesContext(connection) as initial_queries:
            self.client.get(url)
        charge.shares.create(name='B', amount=Decimal('4'))
        with CaptureQueriesContext(connection) as expanded_queries:
            row = self.client.get(url).json()['results'][0]
        self.assertEqual({s['name']: s['has_repayments'] for s in row['shares']}, {'A': True, 'B': False})
        self.assertEqual(len(expanded_queries), len(initial_queries))

    def test_dashboard_does_not_mutate_stale_renewal_dates(self):
        today = timezone.localdate()
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
        today = timezone.localdate()
        self.assertEqual(_days_left_text(today - timedelta(days=1), today), '1 day overdue')
        self.assertEqual(_days_left_text(today - timedelta(days=3), today), '3 days overdue')

    def test_service_color_is_consistent_across_sections(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Spotify',
            category='Music',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=timezone.localdate(),
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

    def test_custom_display_color_is_used_across_sections(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Spotify',
            display_color='#F9F871',
            category='Music',
            billing_cycle='monthly',
            cost=Decimal('9.99'),
            start_date=timezone.localdate(),
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

        self.assertEqual(upcoming['bg_style'], 'background-color: #F9F871;')
        self.assertEqual(subscriptions_item['bg_style'], 'background-color: #F9F871;')
        self.assertEqual(active_item['bg_style'], 'background-color: #F9F871;')

    def test_visible_subscriptions_use_distinct_colors(self):
        for service_name in ['Spotify', 'Netflix', 'Apple TV']:
            Subscription.objects.create(
                user=self.user,
                service_name=service_name,
                category='Streaming',
                billing_cycle='monthly',
                cost=Decimal('10.00'),
                start_date=timezone.localdate(),
                status='active',
            )

        response = self.client.get(reverse('dashboard:home'))
        visible_items = [
            item for item in response.context['subscriptions_panel']
            if not item['is_placeholder']
        ]
        colors = [item['bg_style'] for item in visible_items]

        self.assertEqual(len(colors), len(set(colors)))

    def test_dashboard_teams_scope_uses_team_membership_subscriptions(self):
        teammate = User.objects.create_user(email='teammate@example.com', password='password')
        team = Team.objects.create(name='Ops Team', created_by=teammate)
        TeamMembership.objects.create(team=team, user=teammate, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=team, user=self.user, role=TeamMembership.ROLE_MEMBER)

        Subscription.objects.create(
            user=self.user,
            service_name='Personal Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('12.00'),
            currency='USD',
            start_date=timezone.localdate(),
            status='active',
        )
        Subscription.objects.create(
            user=teammate,
            team=team,
            service_name='Team Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('40.00'),
            currency='USD',
            start_date=timezone.localdate(),
            status='active',
        )

        response = self.client.get(reverse('dashboard:home'), {'scope': 'teams'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['dashboard_scope'], 'teams')
        self.assertEqual(response.context['total_active'], 1)
        self.assertEqual(response.context['monthly_spend'], Decimal('40.00'))
        self.assertEqual(response.context['upcoming_view_all_url'], reverse('accounts:teams_overview'))

    def test_balance_trend_uses_single_currency_when_multiple_present(self):
        usd_subscription = Subscription.objects.create(
            user=self.user,
            service_name='USD Currency Test',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            start_date=timezone.localdate(),
            status='active',
        )
        eur_subscription = Subscription.objects.create(
            user=self.user,
            service_name='EUR Currency Test',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('30.00'),
            start_date=timezone.localdate(),
            status='active',
        )
        transaction_date = timezone.localdate() - timedelta(days=2)

        usd_subscription.transactions.create(
            user=self.user,
            service_name_snapshot='USD Currency Test',
            amount=Decimal('10.00'),
            currency='USD',
            charged_for_date=transaction_date,
        )
        eur_subscription.transactions.create(
            user=self.user,
            service_name_snapshot='EUR Currency Test',
            amount=Decimal('30.00'),
            currency='EUR',
            charged_for_date=transaction_date,
        )

        response = self.client.get(reverse('dashboard:home'))
        points = response.context['balance_trend_points']

        self.assertEqual(response.context['balance_trend_currency'], 'USD')
        self.assertTrue(response.context['balance_trend_has_multiple_currencies'])
        self.assertAlmostEqual(points[-3], 10.00, places=2)

    def test_balance_trend_picks_non_usd_currency_when_only_one_exists(self):
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='Euro Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('7.00'),
            start_date=timezone.localdate(),
            status='active',
        )
        transaction_date = timezone.localdate() - timedelta(days=1)
        subscription.transactions.create(
            user=self.user,
            service_name_snapshot='Euro Service',
            amount=Decimal('7.00'),
            currency='EUR',
            charged_for_date=transaction_date,
        )

        response = self.client.get(reverse('dashboard:home'))
        points = response.context['balance_trend_points']

        self.assertEqual(response.context['balance_trend_currency'], 'EUR')
        self.assertFalse(response.context['balance_trend_has_multiple_currencies'])
        self.assertAlmostEqual(points[-2], 7.00, places=2)

    def test_adjust_balance_respects_scope_for_base_calculation(self):
        teammate = User.objects.create_user(email='owner@example.com', password='password')
        team = Team.objects.create(name='Finance Team', created_by=teammate)
        TeamMembership.objects.create(team=team, user=teammate, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=team, user=self.user, role=TeamMembership.ROLE_MEMBER)

        Subscription.objects.create(
            user=self.user,
            service_name='Personal Budget',
            category='Finance',
            billing_cycle='monthly',
            cost=Decimal('20.00'),
            currency='USD',
            start_date=timezone.localdate(),
            status='active',
        )
        Subscription.objects.create(
            user=teammate,
            team=team,
            service_name='Team Budget',
            category='Finance',
            billing_cycle='monthly',
            cost=Decimal('80.00'),
            currency='USD',
            start_date=timezone.localdate(),
            status='active',
        )

        response = self.client.post(
            reverse('dashboard:adjust_balance'),
            data=json.dumps({'target_balance': '100.00', 'scope': 'teams'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['dashboard_scope'], 'teams')
        self.assertEqual(payload['balance_base_display'], '$80.00')
        self.assertEqual(payload['balance_adjustment_display'], '+$20.00')

        dashboard = reverse('dashboard:home')
        self.assertEqual(self.client.get(dashboard).context['balance_display'], '$20.00')
        self.assertEqual(self.client.get(dashboard, {'scope': 'teams'}).context['balance_display'], '$100.00')

        personal = self.client.post(
            reverse('dashboard:adjust_balance'),
            data=json.dumps({'target_balance': '35.00'}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(personal.status_code, 200, personal.content)
        self.assertEqual(self.client.get(dashboard).context['balance_display'], '$35.00')
        self.assertEqual(self.client.get(dashboard, {'scope': 'teams'}).context['balance_display'], '$100.00')


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

    def test_snoozed_notification_survives_mark_all_read_and_resurfaces(self):
        now = timezone.now()
        snoozed = InAppNotification.objects.create(recipient=self.user, title='Remind me later')
        visible = InAppNotification.objects.create(recipient=self.user, title='Visible now')
        delivery = NotificationDelivery.objects.create(notification=snoozed, deliver_after=now + timedelta(days=1),
                                                        snoozed_until=now + timedelta(days=1))
        for url in ('dashboard_api:notifications', 'dashboard:notifications_list_api'):
            with self.subTest(url=url):
                data = self.client.get(reverse(url)).json()
                self.assertEqual([item['id'] for item in data['notifications']], [visible.pk])
                self.assertEqual(data['unread_count'], 1)
        self.assertNotContains(self.client.get(reverse('dashboard:notifications_page')), snoozed.title)
        for url in ('dashboard_api:read_all', 'dashboard:notifications_mark_all_read_api'):
            with self.subTest(url=url):
                InAppNotification.objects.filter(pk=visible.pk).update(is_read=False, read_at=None)
                self.assertEqual(self.client.post(reverse(url)).json()['unread_count'], 0)
                snoozed.refresh_from_db()
                self.assertFalse(snoozed.is_read)
        delivery.snoozed_until = now - timedelta(minutes=1)
        delivery.save()
        snoozed.last_reminded_at = timezone.now()
        snoozed.save()
        for url in ('dashboard_api:notifications', 'dashboard:notifications_list_api'):
            data = self.client.get(reverse(url)).json()
            self.assertEqual([item['id'] for item in data['notifications']], [snoozed.pk, visible.pk])
            self.assertEqual(data['unread_count'], 1)
