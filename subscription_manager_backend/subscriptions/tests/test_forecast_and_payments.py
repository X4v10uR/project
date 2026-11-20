from datetime import UTC, date, datetime, timedelta
from uuid import uuid4
from decimal import Decimal
from io import BytesIO, TextIOWrapper
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import TeamMembership, User
from accounts.team_workflows import create_team
from dashboard.budgets import check_budgets
from subscriptions.models import InAppNotification, NotificationLog, Subscription, Transaction
from subscriptions.services import BillingService, NotificationService


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', NOTIFICATION_DAYS_BEFORE=3)
class ForecastAndPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tracker@example.test', timezone='UTC')
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.fields = dict(service_name='Studio', category='Work', cost='10.00', currency='PKR',
                           start_date=self.today.isoformat(), billing_cycle='weekly')

    def create(self, **changes):
        response = self.client.post('/api/subscriptions/', {**self.fields, **changes}, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        return Subscription.objects.get(pk=response.json()['id'])

    def dashboard(self, **query):
        response = self.client.get('/api/dashboard/', query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_forecast_counts_all_five_dates_and_excludes_outside_window(self):
        start = self.today + timedelta(days=1)
        self.create(start_date=start.isoformat())
        self.create(start_date=(self.today + timedelta(days=30)).isoformat(), billing_cycle='monthly')
        result = self.dashboard()
        self.assertEqual(result['upcoming_count'], 5)
        self.assertEqual(result['stats_upcoming_bill_balance_display'], 'PKR 50.00')
        self.assertEqual([item['date'] for item in result['upcoming_bills']],
                         [(start + timedelta(weeks=n)).isoformat() for n in range(5)])
        self.assertFalse(Transaction.objects.exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend')
    def test_reminder_command_on_redirected_cp1252_console(self):
        from manage import main

        sub = self.create(service_name='Studio 星', start_date=(self.today + timedelta(days=3)).isoformat())
        with TextIOWrapper(BytesIO(), encoding='cp1252', errors='strict') as output:
            args = ['manage.py', 'send_renewal_notifications']
            with patch.multiple('sys', stdout=output, stderr=output, argv=args):
                main()
                main()
            output.flush()
            log = output.buffer.getvalue().decode('cp1252')
        self.assertIn('Sent: 1', log)
        self.assertIn('Sent: 0', log)
        self.assertEqual(NotificationLog.objects.filter(subscription=sub, delivery_claim__isnull=True).count(), 1)

    def test_quarterly_trial_defers_charges_and_preserves_month_end_anchor(self):
        trial = date(self.today.year + 1, 1, 31)
        sub = self.create(billing_cycle='quarterly', trial_end_date=trial.isoformat(), paid_through=self.today.isoformat(),
                          cancel_by_date=(trial - timedelta(days=2)).isoformat(), cost='30.00')
        self.assertEqual(sub.renewal_date, trial)
        self.assertEqual(self.dashboard()['monthly_spend_by_currency'], {'PKR': '10.00'})
        self.assertEqual(BillingService.record_renewal_charges(trial - timedelta(days=1))['created'], 0)
        self.assertEqual(BillingService.record_renewal_charges(date(trial.year, 7, 31))['created'], 3)
        self.assertCountEqual(sub.transactions.values_list('charged_for_date', flat=True),
                              [trial, date(trial.year, 4, 30), date(trial.year, 7, 31)])
        invalid = self.client.post('/api/subscriptions/', {**self.fields, 'trial_end_date': '2000-01-01'},
                                   content_type='application/json')
        self.assertEqual(invalid.status_code, 400)
        content = self.client.get('/api/subscriptions/export/csv/').content
        self.client.force_login(User.objects.create_user('import@example.test'))
        reply = self.client.post('/api/subscriptions/import/csv/', {
            'mode': 'confirm', 'file': SimpleUploadedFile('plans.csv', content),
        })
        self.assertEqual(reply.json()['imported'], 1)
        restored = Subscription.objects.exclude(pk=sub.pk).get()
        self.assertEqual((restored.trial_end_date, restored.cancel_by_date), (trial, sub.cancel_by_date))
        self.assertEqual(restored.paid_through, self.today)

    def test_team_approval_preserves_trial_and_deadline_and_an_older_client_can_edit(self):
        team = create_team(user=self.user, name='Quarterly team')
        member = User.objects.create_user('requester@example.test')
        TeamMembership.objects.create(team=team, user=member, role='member')
        self.client.force_login(member)
        first_paid = self.today + timedelta(days=14)
        cancel = first_paid - timedelta(days=2)
        fields = {**self.fields, 'billing_cycle': 'quarterly', 'team_id': team.pk, 'paid_through': self.today.isoformat(),
                  'trial_end_date': first_paid.isoformat(), 'cancel_by_date': cancel.isoformat()}
        response = self.client.post('/api/subscriptions/', fields, content_type='application/json')
        self.assertEqual(response.status_code, 202, response.content)
        self.client.force_login(self.user)
        request_id = response.json()['request_id']
        approved = self.client.post(f'/api/accounts/teams/requests/{request_id}/approve/', {},
                                    content_type='application/json')
        self.assertEqual(approved.status_code, 200, approved.content)
        sub = team.subscriptions.get()
        self.assertEqual(sub.renewal_date, first_paid)
        # A full update from a client built before these optional fields existed.
        update = {**self.fields, 'billing_cycle': 'quarterly', 'status': 'active', 'split_type': 'equal'}
        edited = self.client.put(f'/api/subscriptions/{sub.pk}/', update, content_type='application/json')
        self.assertEqual(edited.status_code, 200, edited.content)
        self.assertEqual(edited.json()['cancel_by_date'], cancel.isoformat())
        self.assertEqual(edited.json()['trial_end_date'], first_paid.isoformat())
        self.assertEqual(edited.json()['paid_through'], self.today.isoformat())

    def test_downtime_recovery_sends_actionable_deadlines_once(self):
        first_paid = date(self.today.year + 1, 6, 12)
        sub = self.create(trial_end_date=first_paid.isoformat(), cancel_by_date=first_paid.replace(day=11).isoformat(),
                          billing_cycle='yearly', renewal_time='09:00', reminder_offsets=[3])
        def run(day, hour):
            return NotificationService.send_batch_notifications(
                target_time=datetime(first_paid.year, 6, day, hour, tzinfo=UTC))['sent']
        self.assertEqual(run(8, 8), 0)
        self.assertEqual(run(9, 11), 2)  # Yesterday's cancel-by reminder and today's late renewal reminder.
        self.assertEqual(run(10, 12), 0)
        self.assertEqual(sub.notifications.count(), 2)
        self.assertTrue(any('Cancellation deadline' in email.subject for email in mail.outbox))
        self.assertTrue(any('Trial ends' in email.subject for email in mail.outbox))
        sub.notifications.all().delete()
        self.assertEqual(run(12, 11), 0)  # Both events have passed.

    def test_abandoned_email_claim_recovers_and_completed_delivery_stays_deduplicated(self):
        sub = self.create()
        log = NotificationLog.objects.create(subscription=sub, recipient=self.user, renewal_date=sub.renewal_date,
                                             days_before=3, delivery_claim=uuid4())
        self.assertFalse(NotificationService.send_renewal_reminder(sub))
        NotificationLog.objects.filter(pk=log.pk).update(sent_at=timezone.now() - timedelta(hours=1))
        self.assertTrue(NotificationService.send_renewal_reminder(sub))
        self.assertFalse(NotificationService.send_renewal_reminder(sub))
        self.assertEqual(len(mail.outbox), 1)
        log.refresh_from_db()
        self.assertIsNone(log.delivery_claim)

    def test_charge_outcomes_and_split_snapshots_survive_edits_deletion_and_retries(self):
        sub = self.create(is_shared=True, participants=[{'name': 'Ada'}])
        charge = sub.transactions.get()
        share = charge.shares.get()
        self.assertEqual(share.amount, Decimal('5'))
        self.assertEqual(self.client.delete(f'/api/subscriptions/{sub.pk}/').status_code, 204)
        endpoint = f'/api/dashboard/history/{charge.pk}'
        for status in ('failed', 'paid', 'paid', 'refunded'):
            reply = self.client.patch(endpoint + '/payment/', {'payment_status': status}, content_type='application/json')
            self.assertEqual(reply.status_code, 200, reply.content)
            history = self.client.get('/api/dashboard/history/').json()
            self.assertEqual(history['results'][0]['payment_status'], status)
            self.assertEqual(history['paid_by_currency'], {'PKR': '5.00'} if status == 'paid' else {})
        for _ in range(2):
            self.assertEqual(self.client.patch(endpoint + f'/shares/{share.pk}/', {'reimbursed': True},
                                              content_type='application/json').status_code, 200)
        share.refresh_from_db()
        self.assertTrue(share.reimbursed)
        self.assertEqual(self.client.post(endpoint + '/shares/', {'name': 'Legacy', 'amount': '3'},
                                         content_type='application/json').status_code, 400)
        self.client.force_login(User.objects.create_user('outsider@example.test'))
        self.assertEqual(self.client.patch(endpoint + '/payment/', {'payment_status': 'paid'},
                                          content_type='application/json').status_code, 404)
        self.assertEqual(self.client.patch(endpoint + f'/shares/{share.pk}/', {'reimbursed': False},
                                          content_type='application/json').status_code, 404)

    def test_legacy_charge_share_entry_and_team_permissions(self):
        team = create_team(user=self.user, name='Studio')
        member = User.objects.create_user('member@example.test')
        TeamMembership.objects.create(team=team, user=member, role='member')
        charge = Transaction.objects.create(user=self.user, team=team, service_name_snapshot='Old plan',
                                            charged_for_date=self.today, amount=10)
        url = f'/api/dashboard/history/{charge.pk}/shares/'
        for expected in (201, 200):
            self.assertEqual(self.client.post(url, {'name': 'Lee', 'amount': '4'}, content_type='application/json').status_code, expected)
        self.assertEqual(charge.shares.count(), 1)
        self.client.force_login(member)
        row = self.client.get('/api/dashboard/history/', {'scope': 'teams'}).json()['results'][0]
        self.assertFalse(row['can_edit'])
        self.assertEqual(row['shares'][0]['name'], 'Lee')
        self.assertEqual(self.client.post(url, {'name': 'Jo', 'amount': '1'}, content_type='application/json').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/dashboard/history/{charge.pk}/payment/', {'payment_status': 'paid'},
                                          content_type='application/json').status_code, 404)

    def test_currency_balances_trends_and_recurring_budget_crossings(self):
        self.create(billing_cycle='monthly', currency='USD', cost='100')
        sub = self.create(billing_cycle='monthly')
        self.client.post('/api/dashboard/balance/adjust/', {'currency': 'pkr', 'target_balance': '12'},
                         content_type='application/json')
        local = self.dashboard(currency='PKR')
        self.assertEqual((local['balance_display'], local['balance_trend_points'][-1]), ('PKR 12.00', 10))
        self.assertEqual(self.dashboard(currency='USD')['balance_display'], '$100.00')
        self.assertEqual(self.dashboard(currency='PKR', scope='teams')['balance_display'], 'PKR 0.00')
        self.assertEqual(self.client.get('/api/dashboard/', {'currency': '123'}).status_code, 400)

        def cap(amount):
            response = self.client.put('/api/dashboard/budget/', {'currency': 'PKR', 'monthly_limit': amount},
                                       content_type='application/json')
            self.assertEqual(response.status_code, 204, response.content)

        cap('10')
        alerts = InAppNotification.objects.filter(recipient=self.user, event_type='budget.exceeded')
        self.assertEqual(alerts.count(), 0)
        with self.captureOnCommitCallbacks(execute=True):
            sub.cost = Decimal('11')
            sub.save()
        self.assertEqual(alerts.count(), 1)
        check_budgets()
        self.assertEqual(alerts.count(), 1)
        self.assertTrue(self.dashboard(currency='PKR')['over_budget'])
        cap('20')
        cap('5')
        self.assertEqual(alerts.count(), 2)
        cap(None)
        self.assertIsNone(self.dashboard(currency='PKR')['monthly_limit'])
        self.assertFalse(self.dashboard(currency='PKR')['over_budget'])
