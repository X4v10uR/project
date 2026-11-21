import csv
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import TeamMembership, User
from accounts.team_workflows import create_team, delete_user_account
from subscriptions.models import Subscription, Transaction
from subscriptions.services import BillingService, NotificationService


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class HistoryAndImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner@example.test')
        self.client.force_login(self.user)
        self.history = reverse('dashboard_api:history')
        self.upload = reverse('subscriptions_api:import')

    def plan(self, **changes):
        fields = dict(user=self.user, category='Music', service_name='Radio', start_date=timezone.localdate(),
                      currency='PKR', cost=Decimal('12.34'), billing_cycle='monthly')
        return Subscription.objects.create(**{**fields, **changes})

    def upload_csv(self, content, mode='preview'):
        file = SimpleUploadedFile('plans.csv', content.encode('utf-8-sig'), content_type='text/csv')
        return self.client.post(self.upload, {'file': file, 'mode': mode})

    def test_retired_charges_keep_personal_and_team_scope(self):
        member = User.objects.create_user('member@example.test')
        team = create_team(user=self.user, name='Audio')
        TeamMembership.objects.create(user=member, team=team, role='owner')
        personal = self.plan()
        shared = self.plan(team=team, service_name='Studio')
        BillingService.record_renewal_charges()
        for plan in (personal, shared):
            self.assertEqual(self.client.delete(reverse('subscriptions_api:detail', args=[plan.pk])).status_code, 204)
        result = self.client.get(self.history, {'service': 'adi', 'start': timezone.localdate(), 'end': timezone.localdate()}).json()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['totals_by_currency'], {'PKR': '12.34'})
        self.assertEqual(result['results'][0]['service'], 'Radio')
        self.assertIsNone(result['results'][0]['subscription_id'])
        self.assertEqual(self.client.get(self.history, {'service': 'Studio'}).json()['count'], 0)
        self.assertEqual(self.client.get(self.history, {'start': '2025-03-02', 'end': '2025-03-01'}).status_code, 400)
        self.client.force_login(member)
        self.assertEqual(self.client.get(self.history).json()['count'], 0)
        delete_user_account(self.user)
        self.assertEqual(self.client.get(self.history, {'scope': 'teams'}).json()['results'][0]['service'], 'Studio')
        team.memberships.filter(user=member).delete()
        self.assertEqual(self.client.get(self.history, {'scope': 'teams'}).json()['count'], 0)

    def test_recovery_handles_existing_charge_month_end_and_retry(self):
        start = date(2024, 1, 31)
        sub = self.plan(start_date=start)
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=start)
        sub.transactions.create(user=self.user, charged_for_date=start, amount=sub.cost, currency=sub.currency)
        end = date(2024, 4, 2)
        preview = BillingService.record_renewal_charges(end, dry_run=True)
        self.assertEqual((preview['created'], preview['existing']), (2, 1))
        self.assertEqual(sub.transactions.count(), 1)
        run = BillingService.record_renewal_charges(end)
        self.assertEqual((run['created'], run['existing']), (2, 1))
        self.assertEqual(BillingService.record_renewal_charges(end)['created'], 0)
        self.assertCountEqual(sub.transactions.values_list('charged_for_date', flat=True),
                              [start, date(2024, 2, 29), date(2024, 3, 31)])
        sub.refresh_from_db()
        self.assertEqual(sub.renewal_date, date(2024, 4, 30))

    def test_history_totals_cover_every_page_and_keep_currencies_separate(self):
        plan = self.plan()
        today = timezone.localdate()
        Transaction.objects.bulk_create([
            Transaction(user=self.user, subscription=plan, service_name_snapshot='Radio', amount='2.00',
                        currency='USD' if n == 0 else 'PKR', charged_for_date=today - timedelta(days=n))
            for n in range(52)
        ])
        first = self.client.get(self.history).json()
        second = self.client.get(self.history, {'page': 2}).json()
        self.assertEqual(first['totals_by_currency'], {'USD': '2.00', 'PKR': '102.00'})
        self.assertEqual(second['totals_by_currency'], first['totals_by_currency'])
        self.assertEqual(len(first['results']), 50)
        self.assertEqual(second['results'][0]['date'], (today - timedelta(days=50)).isoformat())
        self.client.logout()
        self.assertEqual(self.client.get(self.history).status_code, 403)

    def test_team_members_receive_one_reminder_each_on_their_local_day(self):
        team = create_team(name='Zones', user=self.user)
        self.user.timezone = 'Asia/Karachi'
        self.user.save(update_fields=['timezone'])
        member = User.objects.create_user('west@example.test', timezone='America/New_York')
        TeamMembership.objects.create(team=team, user=member, role='member')
        day = date(2027, 6, 4)
        self.plan(team=team, start_date=day, renewal_time=time(0, 30))
        for instant, expected in [(datetime(2027, 5, 31, 20, tzinfo=UTC), self.user),
                                  (datetime(2027, 6, 1, 5, tzinfo=UTC), member)]:
            with patch('django.utils.timezone.now', return_value=instant):
                run = NotificationService.send_batch_notifications(target_time=instant.time())
                self.assertEqual(run['sent'], 1)
                self.assertEqual(mail.outbox[-1].to, [expected.email])
                self.assertEqual(NotificationService.send_batch_notifications(target_time=instant.time())['sent'], 0)
        self.assertEqual(len(mail.outbox), 2)

    def test_hourly_job_handles_the_repeated_hour_at_daylight_saving_end(self):
        self.user.timezone = 'America/New_York'
        self.user.save(update_fields=['timezone'])
        self.plan(start_date=date(2027, 11, 10), renewal_time=time(1, 30))
        first = datetime(2027, 11, 7, 5, 45, tzinfo=UTC)
        self.assertEqual(NotificationService.send_batch_notifications(target_time=first)['sent'], 1)
        self.assertEqual(NotificationService.send_batch_notifications(target_time=first + timedelta(hours=1))['sent'], 0)

    def test_team_membership_is_rechecked_when_sending_a_selected_reminder(self):
        team = create_team(name='Team', user=self.user)
        former = User.objects.create_user('former@example.test')
        membership = TeamMembership.objects.create(team=team, user=former, role='member')
        self.plan(team=team, start_date=date(2027, 11, 10), renewal_time=time(9))
        batches = NotificationService.get_subscriptions_due_for_notification(
            target_time=datetime(2027, 11, 7, 9, 30, tzinfo=UTC),
        )
        membership.delete()
        self.assertEqual(len(batches), 1)
        self.assertTrue(NotificationService.send_renewal_reminder(*batches[0]))
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_import_validates_preview_confirm_and_retry(self):
        text = 'Service Name,Billing Cycle,Currency,Total Cost,Start Date\r\n'
        future = timezone.localdate() + timedelta(days=10)
        good = f'"Music, Family",monthly,PKR,999.50,{future}\r\n'
        bad = 'Broken,monthly,USD,-1,2027-03-01\r\n'
        self.assertEqual(self.upload_csv(text + good + bad, 'confirm').status_code, 400)
        self.assertFalse(Subscription.objects.exists())
        preview = self.upload_csv(text + good * 2).json()
        self.assertEqual([row['status'] for row in preview['rows']], ['ready', 'duplicate'])
        self.assertFalse(Subscription.objects.exists())
        for expected in (1, 0):
            self.assertEqual(self.upload_csv(text + good * 2, 'confirm').json()['imported'], expected)
        plan = Subscription.objects.get()
        self.assertEqual((plan.service_name, plan.currency, plan.cost), ('Music, Family', 'PKR', Decimal('999.50')))
        self.assertFalse(Transaction.objects.exists())

    def test_shared_export_restores_custom_shares_and_offsets(self):
        sub = self.plan(service_name='+Radio', notes="'Personal", is_shared=True, split_type='custom',
                        user_cost=Decimal('10.34'), reminders_enabled=False)
        sub.participants.create(name='Ann, Jr.', share_amount=Decimal('2.00'))
        sub.offsets.create(days_before=6)
        content = self.client.get(reverse('subscriptions_api:export')).content.decode()
        self.assertIn('Participant Shares', next(csv.reader(StringIO(content))))
        self.assertEqual(self.upload_csv(content).json()['rows'][0]['status'], 'duplicate')
        self.client.force_login(User.objects.create_user('new@example.test'))
        response = self.upload_csv(content, 'confirm')
        self.assertEqual(response.json()['imported'], 1, response.content)
        imported = Subscription.objects.exclude(pk=sub.pk).get()
        self.assertEqual(imported.user_cost, sub.user_cost)
        self.assertEqual((imported.service_name, imported.notes), ('+Radio', "'Personal"))
        self.assertEqual(imported.participants.get().name, 'Ann, Jr.')
        self.assertEqual(imported.offsets.get().days_before, 6)
        self.assertFalse(imported.reminders_enabled)

    def test_export_transfers_the_effective_regular_price_and_split_during_a_discount(self):
        today = timezone.localdate()
        sub = self.plan(cost=Decimal('12'), user_cost=Decimal('4'), is_shared=True,
                        introductory_cost=Decimal('3'), introductory_until=today + timedelta(days=10),
                        cancellation_notes="'Keep this note")
        for name in ('Ann', 'Bo'):
            sub.participants.create(name=name, share_amount=Decimal('4'))
        sub.price_changes.create(previous_cost=12, cost=20, effective_on=today)
        content = self.client.get(reverse('subscriptions_api:export')).content.decode()
        row = next(csv.DictReader(StringIO(content)))
        self.assertEqual((row['Total Cost'], row['Your Cost']), ('20.00', '6.67'))
        self.assertEqual(json.loads(row['Participant Shares']),
                         [{'name': 'Ann', 'share': '6.67'}, {'name': 'Bo', 'share': '6.66'}])
        self.client.force_login(User.objects.create_user('recipient@example.test'))
        result = self.upload_csv(content, 'confirm')
        self.assertEqual(result.json()['imported'], 1, result.content)
        imported = Subscription.objects.get(user__email='recipient@example.test')
        self.assertEqual(imported.price_on(today), Decimal('3.00'))
        self.assertEqual(imported.price_on(imported.introductory_until), Decimal('20.00'))
        self.assertEqual(imported.cancellation_notes, sub.cancellation_notes)
