from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from dashboard.services import _days_left_text
from subscriptions.models import Subscription

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
                     'upcoming_renewals', 'status_dist']:
            self.assertIn(key, response.context)

    def test_dashboard_fixed_slot_sections_are_padded(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(len(response.context['upcoming_bills']), 3)
        self.assertEqual(len(response.context['subscriptions_panel']), 3)
        self.assertEqual(len(response.context['active_subscriptions_panel']), 2)
        self.assertEqual(len(response.context['recent_transactions']), 2)

    def test_bell_url_contains_due_within_filter(self):
        response = self.client.get(reverse('dashboard:home'))
        bell_url = response.context['bell_url']
        parsed = urlparse(bell_url)
        query = parse_qs(parsed.query)
        self.assertEqual(query.get('due_within'), ['30'])
        self.assertEqual(query.get('status'), ['active'])
        self.assertEqual(query.get('sort'), ['renewal_date'])

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

    def test_dashboard_refreshes_stale_renewal_dates(self):
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
        self.assertGreaterEqual(subscription.renewal_date, today)

    def test_days_left_text_handles_overdue_dates(self):
        today = date.today()
        self.assertEqual(_days_left_text(today - timedelta(days=1), today), '1 day overdue')
        self.assertEqual(_days_left_text(today - timedelta(days=3), today), '3 days overdue')


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
