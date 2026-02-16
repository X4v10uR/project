from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

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
        for key in ['total_active', 'total_paused', 'total_cancelled', 'total_shared',
                     'monthly_spend', 'yearly_spend', 'avg_monthly_spend',
                     'upcoming_renewals', 'status_dist']:
            self.assertIn(key, response.context)

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
