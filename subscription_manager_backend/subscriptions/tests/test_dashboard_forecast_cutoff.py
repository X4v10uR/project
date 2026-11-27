from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from accounts.team_workflows import create_team
from subscriptions.models import PriceChange, Subscription, Transaction
from subscriptions.services import BillingService


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DashboardForecastCutoffTests(TestCase):
    def setUp(self):
        self.west = User.objects.create_user('west@example.test', timezone='America/Los_Angeles')
        self.east = User.objects.create_user('east@example.test', timezone='Asia/Karachi')
        self.today = date(2026, 11, 27)
        self.client.force_login(self.east)

    def sub(self, user=None, **fields):
        defaults = {
            'user': user or self.east, 'service_name': 'Studio', 'category': 'Other',
            'cost': Decimal('30'), 'start_date': self.today, 'billing_cycle': 'monthly', 'currency': 'USD',
        }
        return Subscription.objects.create(**{**defaults, **fields})

    def run_billing(self, instant, *flags):
        with patch('django.utils.timezone.now', return_value=instant):
            call_command('record_subscription_charges', *flags, stdout=StringIO())

    def test_automatic_billing_uses_payer_local_date_for_personal_and_team_plans(self):
        team = create_team(name='Studio Team', user=self.east)
        with patch('django.utils.timezone.now', return_value=datetime(2026, 11, 26, 20, tzinfo=UTC)):
            personal = self.sub(self.east)
            team_plan = self.sub(self.west, team=team)
        self.run_billing(datetime(2026, 11, 26, 20, tzinfo=UTC))
        self.assertEqual(personal.transactions.get().charged_for_date, self.today)
        self.assertFalse(team_plan.transactions.exists())
        self.run_billing(datetime(2026, 11, 27, 1, tzinfo=UTC))
        self.assertFalse(team_plan.transactions.exists())
        self.run_billing(datetime(2026, 11, 27, 8, tzinfo=UTC))
        self.run_billing(datetime(2026, 11, 27, 9, tzinfo=UTC))
        self.assertEqual(team_plan.transactions.get().charged_for_date, self.today)
        self.assertEqual(personal.transactions.count(), 1)

    def test_explicit_backfill_date_is_used_for_every_payer_and_dry_run_does_not_write(self):
        instant = datetime(2026, 11, 26, 12, tzinfo=UTC)
        with patch('django.utils.timezone.now', return_value=instant):
            plan = self.sub(self.west)
        self.run_billing(instant, '--date', self.today.isoformat(), '--dry-run')
        self.assertFalse(plan.transactions.exists())
        self.run_billing(instant, '--date', self.today.isoformat())
        self.assertEqual(plan.transactions.get().charged_for_date, self.today)

    @patch('django.utils.timezone.now', return_value=datetime(2026, 11, 27, 12, tzinfo=UTC))
    def test_dashboard_and_insights_retain_an_unpaid_charge_after_recording_and_use_future_prices(self, _now):
        sub = self.sub()
        PriceChange.objects.create(subscription=sub, previous_cost=30, cost=40, effective_on=date(2026, 12, 1))

        def snapshot():
            dashboard = self.client.get('/api/dashboard/', {'currency': 'USD'}).json()
            insights = self.client.get('/api/subscriptions/insights/').json()['totals'][0]
            return dashboard, insights

        before, insight_before = snapshot()
        self.assertEqual(before['upcoming_week']['amount'], '$30.00')
        self.assertEqual((before['yearly_spend'], insight_before['annual_projection']), ('470.00', '470.00'))
        self.assertEqual(BillingService.record_renewal_charges(self.today)['created'], 1)
        charge = sub.transactions.get()
        self.assertEqual(charge.payment_status, Transaction.PaymentStatus.SCHEDULED)
        after, insight_after = snapshot()
        self.assertEqual(before['upcoming_count'], after['upcoming_count'])
        self.assertEqual(before['upcoming_week'], after['upcoming_week'])
        self.assertEqual(insight_before, insight_after)

        Transaction.objects.filter(pk=charge.pk).update(payment_status=Transaction.PaymentStatus.PAID)
        settled, insight_settled = snapshot()
        self.assertEqual(settled['upcoming_week']['amount'], '$0.00')
        self.assertEqual((settled['yearly_spend'], insight_settled['annual_projection']), ('440.00', '440.00'))
        self.assertEqual(insight_settled['month_paid'], '30.00')
