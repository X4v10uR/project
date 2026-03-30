import csv
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from subscriptions.models import ReminderOffset, Subscription, SubscriptionParticipant, Transaction
from subscriptions.services import BillingService

User = get_user_model()


class SubscriptionListAndPrefillTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='filters@example.com', password='password')
        self.client.force_login(self.user)

    def test_due_within_filter_limits_by_renewal_window(self):
        today = date.today()
        near = Subscription.objects.create(
            user=self.user,
            service_name='Near Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            start_date=today,
            status='active',
        )
        far = Subscription.objects.create(
            user=self.user,
            service_name='Far Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('12.00'),
            start_date=today,
            status='active',
        )

        Subscription.objects.filter(pk=near.pk).update(renewal_date=today + timedelta(days=7))
        Subscription.objects.filter(pk=far.pk).update(renewal_date=today + timedelta(days=60))

        response = self.client.get(reverse('subscriptions:list'), {'due_within': 30})
        subs = list(response.context['subscriptions'])
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].pk, near.pk)

    def test_invalid_due_within_is_ignored_and_not_marked_active(self):
        Subscription.objects.create(
            user=self.user,
            service_name='Single Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            start_date=date.today(),
            status='active',
        )

        response = self.client.get(reverse('subscriptions:list'), {'due_within': 'abc'})

        self.assertEqual(response.context['due_within'], '')
        self.assertFalse(response.context['filters_active'])
        self.assertEqual(
            response.context['subscriptions_filtered_total'],
            response.context['subscriptions_total'],
        )
        self.assertNotContains(response, 'Due within abc')

    def test_shared_filter_false_returns_only_solo_subscriptions(self):
        today = date.today()
        shared = Subscription.objects.create(
            user=self.user,
            service_name='Shared Plan',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('15.00'),
            is_shared=True,
            start_date=today,
            status='active',
        )
        solo = Subscription.objects.create(
            user=self.user,
            service_name='Solo Plan',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('9.00'),
            is_shared=False,
            start_date=today,
            status='active',
        )
        SubscriptionParticipant.objects.create(
            subscription=shared,
            name='Alex',
            share_amount=Decimal('5.00'),
        )

        response = self.client.get(reverse('subscriptions:list'), {'shared': 'false'})
        subs = list(response.context['subscriptions'])

        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].pk, solo.pk)

    def test_mixed_currency_metrics_use_safe_display_and_count_share(self):
        today = date.today()
        Subscription.objects.create(
            user=self.user,
            service_name='USD Active',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            currency='USD',
            start_date=today,
            status='active',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='PKR Active',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('3000.00'),
            currency='PKR',
            start_date=today,
            status='active',
        )

        response = self.client.get(reverse('subscriptions:list'))
        stats = response.context['subscriptions_stats']
        burn_metrics = response.context['subscriptions_burn_metrics']

        self.assertTrue(stats['monthly_spend_is_mixed'])
        self.assertEqual(stats['monthly_spend_display'], 'Multiple currencies')
        self.assertTrue(burn_metrics['spend_is_mixed'])
        self.assertEqual(burn_metrics['active_share_basis'], 'count')
        self.assertEqual(burn_metrics['active_share_percent'], 100)

    def test_create_form_prefills_safe_query_params(self):
        response = self.client.get(
            reverse('subscriptions:create'),
            {
                'service_name': 'Spotify',
                'category': 'Music',
                'billing_cycle': 'monthly',
                'plan_name': 'Family',
                'invalid_field': 'ignored',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.initial['service_name'], 'Spotify')
        self.assertEqual(form.initial['category'], 'Music')
        self.assertEqual(form.initial['billing_cycle'], 'monthly')
        self.assertEqual(form.initial['plan_name'], 'Family')
        self.assertNotIn('invalid_field', form.initial)

    def test_export_csv_respects_filters(self):
        today = date.today()
        Subscription.objects.create(
            user=self.user,
            service_name='Active Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            start_date=today,
            status='active',
        )
        Subscription.objects.create(
            user=self.user,
            service_name='Paused Service',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('12.00'),
            start_date=today,
            status='paused',
        )

        response = self.client.get(reverse('subscriptions:export_csv'), {'status': 'active'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment;', response['Content-Disposition'])

        content = response.content.decode('utf-8')
        rows = list(csv.DictReader(content.splitlines()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Service Name'], 'Active Service')
        self.assertEqual(rows[0]['Status'], 'active')

    def test_export_csv_sanitizes_formula_cells(self):
        today = date.today()
        subscription = Subscription.objects.create(
            user=self.user,
            service_name='=cmd',
            plan_name='@team',
            category='+tools',
            billing_cycle='monthly',
            cost=Decimal('10.00'),
            start_date=today,
            status='active',
            account_email='  -email@example.com',
            notes='=1+1',
        )
        SubscriptionParticipant.objects.create(
            subscription=subscription,
            name='  =participant',
        )

        response = self.client.get(reverse('subscriptions:export_csv'))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode('utf-8')
        rows = list(csv.DictReader(content.splitlines()))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['Service Name'], "'=cmd")
        self.assertEqual(row['Plan Name'], "'@team")
        self.assertEqual(row['Category'], "'+tools")
        self.assertEqual(row['Participants'], "'  =participant")
        self.assertEqual(row['Account Email'], "'  -email@example.com")
        self.assertEqual(row['Notes'], "'=1+1")


class BillingServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='billing@example.com', password='password')

    def test_records_transaction_for_due_subscription(self):
        today = date.today()
        sub = Subscription.objects.create(
            user=self.user,
            service_name='Netflix',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('19.99'),
            start_date=today,
            status='active',
        )
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=today)

        results = BillingService.record_renewal_charges(target_date=today)

        self.assertEqual(results['created'], 1)
        self.assertEqual(Transaction.objects.count(), 1)
        txn = Transaction.objects.get()
        self.assertEqual(txn.amount, Decimal('19.99'))
        self.assertEqual(txn.charged_for_date, today)

    def test_shared_subscription_uses_user_cost_for_transaction(self):
        today = date.today()
        sub = Subscription.objects.create(
            user=self.user,
            service_name='Family Plan',
            category='Streaming',
            billing_cycle='monthly',
            cost=Decimal('15.00'),
            user_cost=Decimal('5.00'),
            is_shared=True,
            start_date=today,
            status='active',
        )
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=today, user_cost=Decimal('5.00'))

        BillingService.record_renewal_charges(target_date=today)
        txn = Transaction.objects.get(subscription=sub)
        self.assertEqual(txn.amount, Decimal('5.00'))

    def test_record_subscription_charges_command_runs(self):
        today = date.today()
        sub = Subscription.objects.create(
            user=self.user,
            service_name='Command Service',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('7.00'),
            start_date=today,
            status='active',
        )
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=today)

        call_command('record_subscription_charges', '--date', today.isoformat())

        self.assertTrue(Transaction.objects.filter(subscription=sub).exists())

    def test_same_day_second_run_keeps_advanced_renewal_date(self):
        today = date.today()
        sub = Subscription.objects.create(
            user=self.user,
            service_name='No Rollback Service',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('8.00'),
            start_date=today,
            status='active',
        )
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=today)

        first_results = BillingService.record_renewal_charges(target_date=today)
        self.assertEqual(first_results['created'], 1)

        sub.refresh_from_db()
        expected_next = today + relativedelta(months=1)
        self.assertEqual(sub.renewal_date, expected_next)

        second_results = BillingService.record_renewal_charges(target_date=today)
        self.assertEqual(second_results['total'], 0)
        self.assertEqual(second_results['created'], 0)
        self.assertEqual(second_results['existing'], 0)

        sub.refresh_from_db()
        self.assertEqual(sub.renewal_date, expected_next)
        self.assertEqual(
            Transaction.objects.filter(subscription=sub, charged_for_date=today).count(),
            1,
        )

    def test_edit_after_charge_same_day_keeps_advanced_renewal_date(self):
        today = date.today()
        sub = Subscription.objects.create(
            user=self.user,
            service_name='Same Day Edit Service',
            category='Utilities',
            billing_cycle='monthly',
            cost=Decimal('8.00'),
            start_date=today,
            status='active',
        )
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=today)

        BillingService.record_renewal_charges(target_date=today)

        sub.refresh_from_db()
        expected_next = today + relativedelta(months=1)
        self.assertEqual(sub.renewal_date, expected_next)

        sub.notes = 'Edited on renewal day after charge capture'
        sub.save()

        sub.refresh_from_db()
        self.assertEqual(sub.renewal_date, expected_next)

    def test_send_notifications_command_without_days_before_honors_custom_offsets(self):
        today = date.today()
        renewal_date = today + timedelta(days=7)
        start_date = renewal_date - relativedelta(months=1)

        sub = Subscription.objects.create(
            user=self.user,
            service_name='Custom Offset Service',
            category='Software',
            billing_cycle='monthly',
            cost=Decimal('14.99'),
            start_date=start_date,
            status='active',
            reminders_enabled=True,
        )
        ReminderOffset.objects.create(subscription=sub, days_before=7)

        out = StringIO()
        call_command('send_renewal_notifications', '--dry-run', stdout=out)
        output = out.getvalue()

        self.assertIn('Custom Offset Service', output)
        self.assertIn('offset: 7', output)
