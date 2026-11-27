from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, TeamMembership
from accounts.team_workflows import create_team
from subscriptions.models import ChargeShare, PriceChange, Subscription, SubscriptionParticipant, Transaction
from subscriptions.services import BillingService, NotificationService, renewals_between


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PlanningTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('planner@example.test', 'ExamplePassword42!')
        self.other = User.objects.create_user('other@example.test', 'ExamplePassword42!')
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def sub(self, **fields):
        return Subscription.objects.create(**{'user': self.user, 'service_name': 'Studio', 'category': 'Software',
            'cost': Decimal('30'), 'billing_cycle': 'monthly', 'start_date': self.today, **fields})

    def post(self, url, fields):
        return self.client.post('/api/subscriptions/' + url, fields, content_type='application/json')

    def test_quick_add_needs_only_four_fields(self):
        result = self.post('', {'service_name': 'Music', 'cost': '9', 'billing_cycle': 'fourweekly', 'start_date': str(self.today + timedelta(days=1))})
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['category'], 'Other')
        self.assertFalse(Transaction.objects.exists())

    def test_halfyearly_and_28_day_schedules_keep_the_anchor(self):
        sub = self.sub(start_date=date(2024, 8, 31), billing_cycle='halfyearly')
        self.assertEqual(list(renewals_between(sub, date(2025, 1, 1), date(2025, 12, 31), use_cursor=False)), [date(2025, 2, 28), date(2025, 8, 31)])
        sub.billing_cycle = 'fourweekly'
        self.assertEqual(sub.calculate_renewal_date(date(2024, 9, 29)), date(2024, 10, 26))

    def test_price_and_intro_discount_are_used_when_recording_charges(self):
        sub = self.sub(billing_cycle='weekly', introductory_cost='5', introductory_until=self.today + timedelta(days=7))
        PriceChange.objects.create(subscription=sub, previous_cost=30, cost=40, effective_on=self.today + timedelta(days=14))
        BillingService.record_renewal_charges(self.today + timedelta(days=14))
        self.assertEqual(list(sub.transactions.order_by('charged_for_date').values_list('amount', flat=True)), [Decimal('5'), Decimal('30'), Decimal('40')])

    def test_scheduled_pause_skips_charges_and_resume_keeps_original_cadence(self):
        sub = self.sub(billing_cycle='weekly', pause_from=self.today + timedelta(days=7), resume_on=self.today + timedelta(days=20))
        BillingService.record_renewal_charges(self.today + timedelta(days=28))
        self.assertEqual(list(sub.transactions.order_by('charged_for_date').values_list('charged_for_date', flat=True)), [self.today, self.today + timedelta(days=21), self.today + timedelta(days=28)])
        sub.refresh_from_db()
        self.assertEqual(sub.renewal_date, self.today + timedelta(days=35))

    def test_paused_subscription_with_resume_date_is_billed_after_resuming(self):
        sub = self.sub(billing_cycle='weekly', status='paused', resume_on=self.today + timedelta(days=6))
        BillingService.record_renewal_charges(self.today + timedelta(days=7))
        self.assertEqual(sub.transactions.count(), 1)

    def test_first_post_resume_charge_and_reminder_use_the_same_schedule(self):
        anchor = self.today
        resumed = self.sub(billing_cycle='weekly', status='paused', resume_on=anchor + timedelta(days=6))
        self.sub(billing_cycle='weekly', status='paused')
        self.sub(billing_cycle='weekly', status='paused', resume_on=anchor + timedelta(days=14))
        self.user.timezone = 'UTC'
        self.user.save(update_fields=['timezone'])
        instant = datetime.combine(anchor + timedelta(days=4), time(16), UTC)
        due = NotificationService.get_subscriptions_due_for_notification(target_time=instant)
        self.assertEqual([(sub.pk, sub.renewal_date) for sub, _ in due], [(resumed.pk, anchor + timedelta(days=7))])
        self.assertTrue(NotificationService.send_renewal_reminder(*due[0]))
        self.assertFalse(NotificationService.send_renewal_reminder(*due[0]))
        BillingService.record_renewal_charges(anchor + timedelta(days=7))
        self.assertEqual(list(Transaction.objects.values_list('subscription_id', flat=True)), [resumed.pk])

    def test_calendar_includes_deadlines_and_exports_valid_folded_events(self):
        sub = self.sub(service_name='Very long name ' * 10, trial_end_date=self.today + timedelta(days=3), cancel_by_date=self.today + timedelta(days=2))
        events = self.client.get('/api/subscriptions/calendar/').json()['events']
        self.assertTrue({'payment', 'trial', 'deadline'} <= {event['kind'] for event in events})
        response = self.client.get('/api/subscriptions/calendar/export/', HTTP_ACCEPT='text/calendar')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'].split(';')[0], 'text/calendar')
        exported = response.content.decode()
        self.assertIn('BEGIN:VCALENDAR\r\n', exported)
        self.assertIn('DTSTART;VALUE=DATE:', exported)
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in exported.split('\r\n')))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/subscriptions/calendar/').json()['events'], [])

    def test_insights_separate_currencies_and_scheduled_from_paid(self):
        sub = self.sub(start_date=self.today + timedelta(days=1))
        self.sub(service_name='Second', currency='PKR', cost=100, start_date=self.today + timedelta(days=1))
        Transaction.objects.create(user=self.user, subscription=sub, charged_for_date=self.today, amount=12, currency='USD', payment_status='paid')
        result = self.client.get('/api/subscriptions/insights/').json()
        totals = {row['currency']: row for row in result['totals']}
        self.assertEqual(totals['USD']['month_paid'], '12.00')
        self.assertEqual(totals['USD']['monthly_commitment'], '30.00')
        self.assertEqual(totals['PKR']['monthly_commitment'], '100.00')

    def test_review_duplicates_trial_and_batch_pause_permissions(self):
        sub = self.sub(trial_end_date=self.today + timedelta(days=3))
        self.sub()
        items = self.client.get('/api/subscriptions/review/').json()['items']
        self.assertEqual(len(items), 2)
        self.assertTrue(any('Trial becomes paid' in reason for item in items for reason in item['reasons']))
        foreign = self.sub(user=self.other)
        response = self.post('review/action/', {'action': 'pause', 'ids': [sub.pk, foreign.pk]})
        self.assertEqual(response.status_code, 404)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'active')
        self.assertEqual(self.post('review/action/', {'action': 'review', 'ids': [sub.pk], 'usage_rating': 'often'}).status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.last_reviewed_on, self.today)

    def test_review_pause_catches_up_using_the_previous_pause_dates(self):
        start = self.today - timedelta(weeks=3)
        sub = self.sub(billing_cycle='weekly', start_date=start,
                       pause_from=start + timedelta(weeks=1), resume_on=start + timedelta(weeks=2))
        Subscription.objects.filter(pk=sub.pk).update(renewal_date=start)
        result = self.post('review/action/', {'action': 'pause', 'ids': [sub.pk]})
        self.assertEqual(result.status_code, 200, result.content)
        BillingService.record_renewal_charges(self.today)
        self.assertCountEqual(sub.transactions.values_list('charged_for_date', flat=True),
                              [start, start + timedelta(weeks=2)])

    def test_pausing_again_after_scheduled_resume_stops_future_charges(self):
        sub = self.sub(billing_cycle='weekly', resume_on=self.today - timedelta(days=1))
        result = self.post(f'{sub.pk}/status/', {'status': 'paused'})
        self.assertEqual(result.status_code, 200, result.content)
        BillingService.record_renewal_charges(self.today + timedelta(weeks=1))
        self.assertFalse(sub.transactions.exists())

    def test_edit_form_can_pause_and_resume_without_reusing_expired_dates(self):
        sub = self.sub(billing_cycle='weekly', pause_from=self.today - timedelta(weeks=2),
                       resume_on=self.today - timedelta(weeks=1))
        url = f'/api/subscriptions/{sub.pk}/'
        fields = self.client.get(url).json()
        for status in ('paused', 'active'):
            fields['status'] = status
            result = self.client.put(url, fields, content_type='application/json')
            self.assertEqual(result.status_code, 200, result.content)
            fields = result.json()
            sub.refresh_from_db()
            self.assertEqual(sub.bills_on(self.today), status == 'active')
            self.assertIsNone(sub.resume_on)

        fields.update(status='paused', pause_from=str(self.today), resume_on=str(self.today + timedelta(weeks=1)))
        result = self.client.put(url, fields, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        sub.refresh_from_db()
        self.assertTrue(sub.bills_on(self.today + timedelta(weeks=1)))

    def test_calendar_ranges_at_the_last_supported_year(self):
        for params in ({'start': '9999-12-01'}, {'start': '9999-12-01', 'end': '9999-12-31'}):
            with self.subTest(params=params):
                result = self.client.get('/api/subscriptions/calendar/', params)
                self.assertEqual(result.status_code, 200, result.content)
                self.assertEqual(result.json()['events'], [])

    def test_price_change_validates_dates_and_ownership(self):
        sub = self.sub()
        response = self.post(f'{sub.pk}/prices/', {'cost': '40', 'effective_on': str(self.today + timedelta(days=10))})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(sub.price_on(self.today), Decimal('30'))
        self.assertEqual(sub.price_on(self.today + timedelta(days=10)), Decimal('40'))
        self.assertEqual(self.post(f'{sub.pk}/prices/', {'cost': '42', 'effective_on': str(self.today)}).status_code, 400)
        self.client.force_login(self.other)
        self.assertEqual(self.post(f'{sub.pk}/prices/', {'cost': '42', 'effective_on': str(self.today + timedelta(days=20))}).status_code, 404)

    def test_price_history_reports_current_regular_cost_separately_from_intro_price(self):
        sub = self.sub(introductory_cost='5', introductory_until=self.today + timedelta(days=7))
        url = f'{sub.pk}/prices/'
        result = self.post(url, {'cost': '40', 'effective_on': str(self.today)})
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['current_regular_cost'], '40.00')
        result = self.post(url, {'cost': '50', 'effective_on': str(self.today + timedelta(days=14))})
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['current_regular_cost'], '40.00')
        self.assertEqual(self.client.get('/api/subscriptions/' + url).json()['current_regular_cost'], '40.00')
        sub.refresh_from_db()
        self.assertEqual(sub.price_on(self.today), Decimal('5'))

    def test_edit_uses_regular_price_without_overwriting_discount_or_effective_increase(self):
        sub = self.sub(introductory_cost='5', introductory_until=self.today + timedelta(days=7))
        PriceChange.objects.create(subscription=sub, previous_cost=30, cost=40, effective_on=self.today)
        detail = self.client.get(f'/api/subscriptions/{sub.pk}/').json()
        self.assertEqual(detail['cost'], '40.00')
        self.assertEqual(detail['current_cost'], '5.00')
        legacy_edit = self.client.get(reverse('subscriptions:update', args=[sub.pk]))
        self.assertEqual(legacy_edit.context['cost_value'], '40.00')
        detail.update(cost='40.00', reminder_offsets=[], participants=[])
        response = self.client.put(f'/api/subscriptions/{sub.pk}/', detail, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        sub.refresh_from_db()
        self.assertEqual(sub.price_on(self.today), Decimal('5'))
        self.assertEqual(sub.price_on(self.today + timedelta(days=8)), Decimal('40'))
        self.assertEqual(sub.price_changes.count(), 1)

    def test_editing_todays_price_updates_the_next_price_change(self):
        sub = self.sub()
        future = self.today + timedelta(weeks=2)
        self.assertEqual(self.post(f'{sub.pk}/prices/', {'cost': '50', 'effective_on': str(future)}).status_code, 201)
        detail_url = f'/api/subscriptions/{sub.pk}/'
        fields = self.client.get(detail_url).json()
        for price in ('35.00', '40.00'):
            fields['cost'] = price
            result = self.client.put(detail_url, fields, content_type='application/json')
            self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(sub.price_changes.get(effective_on=future).previous_cost, Decimal('40.00'))
        # Previously saved schedules may still contain the old quote.
        sub.price_changes.filter(effective_on=future).update(previous_cost=30)
        changes = self.client.get(detail_url + 'prices/').json()['changes']
        self.assertEqual([(c['previous_cost'], c['cost']) for c in changes],
                         [('30.00', '40.00'), ('40.00', '50.00')])
        reasons = self.client.get('/api/subscriptions/review/').json()['items'][0]['reasons']
        self.assertTrue(any('USD 40.00 to 50.00' in reason for reason in reasons))

    def test_future_price_cannot_make_custom_shares_exceed_the_bill(self):
        sub = self.sub(is_shared=True, split_type='custom', user_cost=10)
        SubscriptionParticipant.objects.create(subscription=sub, name='Alex', share_amount=20)
        response = self.post(f'{sub.pk}/prices/', {'cost': '15', 'effective_on': str(self.today + timedelta(days=10))})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(sub.price_changes.exists())

    def test_partial_repayment_is_bounded_logged_and_included_in_balances(self):
        sub = self.sub()
        charge = Transaction.objects.create(user=self.user, subscription=sub, charged_for_date=self.today, amount=15, payment_status='paid')
        share = ChargeShare.objects.create(charge=charge, name='Alex', amount=15)
        self.assertEqual(self.post(f'settlements/{share.pk}/repay/', {'amount': '5', 'note': 'Cash'}).status_code, 201)
        self.assertEqual(self.client.get('/api/subscriptions/settlements/').json()['balances'][0]['outstanding'], '10.00')
        self.assertEqual(self.post(f'settlements/{share.pk}/repay/', {'amount': '11'}).status_code, 400)
        self.assertEqual(self.post(f'settlements/{share.pk}/repay/', {'amount': '10'}).status_code, 201)
        share.refresh_from_db()
        self.assertTrue(share.reimbursed)
        self.assertEqual(share.repayments.count(), 2)
        self.assertEqual(self.client.patch(f'/api/dashboard/history/{charge.pk}/shares/{share.pk}/', {'reimbursed': False}, content_type='application/json').status_code, 400)

    def test_team_member_link_validates_membership_and_owner_writes(self):
        team = create_team(name='Studio', user=self.user)
        TeamMembership.objects.create(team=team, user=self.other, role='member')
        result = self.post('', {'service_name': 'Shared', 'cost': '30', 'billing_cycle': 'monthly', 'start_date': str(self.today), 'team_id': team.pk, 'is_shared': True, 'participants': [{'name': 'Other', 'member_id': self.other.pk}]})
        self.assertEqual(result.status_code, 201, result.content)
        sub = Subscription.objects.get(pk=result.json()['id'])
        self.assertEqual(sub.participants.get().member_id, self.other.pk)
        self.assertEqual(sub.transactions.get().shares.get().member_id, self.other.pk)
        self.client.force_login(self.other)
        self.assertEqual(self.post('review/action/', {'action': 'pause', 'ids': [sub.pk]}).status_code, 404)

    def test_cancellation_requested_keeps_billing_confirmed_stops_it(self):
        fields = {'service_name': 'Cancel me', 'cost': '10', 'billing_cycle': 'weekly', 'start_date': str(self.today), 'cancellation_state': 'requested'}
        result = self.post('', fields)
        self.assertEqual(result.status_code, 201, result.content)
        sub = Subscription.objects.get(pk=result.json()['id'])
        self.assertTrue(sub.bills_on(self.today))
        result = self.client.put(f'/api/subscriptions/{sub.pk}/', {**fields, 'cancellation_state': 'confirmed', 'currency': 'USD', 'status': 'active', 'split_type': 'equal'}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'cancelled')
        self.assertEqual(list(renewals_between(sub, self.today, self.today + timedelta(days=30))), [])

    @patch('subscriptions.planning.timezone.localdate', return_value=date(2026, 11, 26))
    def test_renewal_comparison_uses_effective_prices_and_creates_no_records(self, _today):
        sub = self.sub(start_date=date(2026, 12, 1), introductory_cost='30',
            introductory_until=date(2027, 1, 1), cancel_by_date=date(2026, 11, 30), currency='USD')
        PriceChange.objects.create(subscription=sub, previous_cost='30', cost='40', effective_on=date(2027, 1, 1))
        before = Subscription.objects.values().get(pk=sub.pk)
        result = self.post(f'{sub.pk}/renewal-comparison/', {'option': 'annual', 'quoted_price': '300'})
        self.assertEqual(result.status_code, 200, result.content)
        data = result.json()
        self.assertEqual(data['keep'], {'next_date': '2026-12-01', 'next_amount': '30.00', 'total': '470.00'})
        self.assertEqual(data['alternative'], {'next_date': '2026-12-01', 'next_amount': '300.00', 'total': '300.00'})
        self.assertEqual((data['total_savings'], data['next_payment_change'], data['cancel_by_date']),
            ('170.00', '270.00', '2026-11-30'))
        self.assertEqual(Subscription.objects.values().get(pk=sub.pk), before)
        self.assertEqual(sub.price_changes.count(), 1)
        self.assertFalse(sub.transactions.exists())

    @patch('subscriptions.planning.timezone.localdate', return_value=date(2027, 1, 31))
    def test_renewal_comparison_skips_recorded_renewal_and_respects_window(self, _today):
        sub = self.sub(start_date=date(2027, 1, 31), currency='USD')
        Transaction.objects.create(user=self.user, subscription=sub, service_name_snapshot=sub.service_name,
            charged_for_date=date(2027, 1, 31), amount=30, currency='USD')
        data = self.post(f'{sub.pk}/renewal-comparison/', {'option': 'downgrade', 'quoted_price': '20'}).json()
        self.assertEqual(data['effective_on'], '2027-02-28')
        self.assertEqual(data['until_date'], '2028-01-31')
        self.assertEqual(data['keep']['total'], '330.00')
        self.assertEqual(data['alternative']['total'], '220.00')
        self.assertIsNone(data['cancel_by_date'])
        cancel = self.post(f'{sub.pk}/renewal-comparison/', {'option': 'cancel'}).json()
        self.assertEqual(cancel['alternative'], {'next_date': None, 'next_amount': '0.00', 'total': '0.00'})
        self.assertEqual(sub.transactions.count(), 1)

    def test_renewal_comparison_permissions_options_and_amount_validation(self):
        personal = self.sub(service_name='Eligible')
        shared = self.sub(service_name='Shared', is_shared=True, split_type='equal')
        other = self.sub(service_name='Private', user=self.other)
        team = self.sub(service_name='Team', team=create_team(name='Studio', user=self.user))
        options = self.client.get('/api/subscriptions/review/').json()['comparison_options']
        self.assertEqual([row['id'] for row in options], [personal.pk])
        for sub in [shared, other, team]:
            self.assertEqual(self.post(f'{sub.pk}/renewal-comparison/', {'option': 'cancel'}).status_code, 404)
        for invalid in [{}, {'quoted_price': '-0.01'}, {'quoted_price': '1.001'}]:
            self.assertEqual(self.post(f'{personal.pk}/renewal-comparison/',
                {'option': 'annual', **invalid}).status_code, 400)

    @patch('subscriptions.planning.timezone.localdate', return_value=date(2026, 11, 27))
    def test_renewal_comparison_rejects_an_empty_projection_without_creating_charges(self, _today):
        sub = self.sub(start_date=date(2026, 12, 1), pause_from=date(2026, 11, 27),
                       resume_on=date(2028, 1, 1))
        result = self.post(f'{sub.pk}/renewal-comparison/', {'option': 'cancel'})
        self.assertEqual(result.status_code, 400, result.content)
        self.assertIn('There is no unrecorded renewal in the next 12 months.', result.json())
        self.assertFalse(sub.transactions.exists())

    @patch('django.utils.timezone.now', return_value=datetime(2026, 11, 27, 12, tzinfo=UTC))
    def test_calendar_keeps_the_same_event_when_a_scheduled_charge_enters_the_ledger(self, _now):
        day = date(2026, 11, 27)
        sub = self.sub(start_date=day, currency='USD')
        query = {'start': day.isoformat(), 'end': day.isoformat()}
        event_id = f'{sub.pk}-payment-{day}'
        uid = f'UID:{self.user.pk}-{event_id}@subly'
        feed = self.client.post('/api/finance/calendar/feeds/', {'scope': 'personal'}, content_type='application/json')
        self.assertEqual(feed.status_code, 201, feed.content)
        feed_url = '/api/finance/calendar/' + feed.json()['url'].rsplit('/', 1)[-1]

        before = self.client.get('/api/subscriptions/calendar/', query).json()['events']
        self.assertEqual([(event['id'], event['amount']) for event in before], [(event_id, '30.00')])
        self.assertEqual(BillingService.record_renewal_charges(day)['created'], 1)
        sub.refresh_from_db()
        self.assertGreater(sub.renewal_date, day)
        charge = sub.transactions.get()
        self.assertEqual(charge.payment_status, Transaction.PaymentStatus.SCHEDULED)
        after = self.client.get('/api/subscriptions/calendar/', query).json()['events']
        self.assertEqual(after, before)

        file = self.client.get('/api/subscriptions/calendar/export/', query, HTTP_ACCEPT='text/calendar')
        self.assertEqual(file.status_code, 200, file.content)
        self.assertEqual(file.content.decode().count(uid), 1)
        self.client.logout()
        live = self.client.get(feed_url, HTTP_ACCEPT='text/calendar')
        self.assertEqual(live.status_code, 200, live.content)
        self.assertEqual(live.content.decode().count(uid), 1)

    @patch('django.utils.timezone.now', return_value=datetime(2026, 11, 27, 12, tzinfo=UTC))
    def test_calendar_uses_ledger_snapshot_and_does_not_resurface_non_scheduled_charges(self, _now):
        day = date(2026, 11, 27)
        sub = self.sub(start_date=day, currency='USD')
        # Leave the cursor on the date deliberately to cover overlapping forecast and ledger.
        charge = Transaction.objects.create(subscription=sub, user=self.user, charged_for_date=day,
            service_name_snapshot='Recorded Studio', amount=Decimal('25.00'), currency='USD')
        query = {'start': day.isoformat(), 'end': day.isoformat()}
        url = '/api/subscriptions/calendar/'
        rows = self.client.get(url, query).json()['events']
        self.assertEqual([(row['service'], row['amount']) for row in rows], [('Recorded Studio', '25.00')])
        for state in (Transaction.PaymentStatus.PAID, Transaction.PaymentStatus.FAILED, Transaction.PaymentStatus.REFUNDED):
            with self.subTest(state=state):
                Transaction.objects.filter(pk=charge.pk).update(payment_status=state)
                self.assertEqual(self.client.get(url, query).json()['events'], [])

    @patch('django.utils.timezone.now', return_value=datetime(2026, 11, 27, 12, tzinfo=UTC))
    def test_calendar_only_shows_scheduled_charges_in_the_requested_visible_workspace(self, _now):
        day = date(2026, 11, 27)
        team = create_team(name='Other team', user=self.other)
        personal = self.sub(start_date=day, service_name='Personal')
        teamed = self.sub(start_date=day, service_name='Team', team=team, user=self.other)
        third = self.sub(start_date=day, service_name='Other personal', user=self.other)
        for sub in (personal, teamed, third):
            Transaction.objects.create(subscription=sub, team=sub.team, user=sub.user, charged_for_date=day,
                service_name_snapshot=sub.service_name, amount=Decimal('30.00'), currency='USD')
            Subscription.objects.filter(pk=sub.pk).update(renewal_date=date(2026, 12, 27))

        url = '/api/subscriptions/calendar/'
        query = {'start': day.isoformat(), 'end': day.isoformat()}
        def ids(scope):
            result = self.client.get(url, {**query, 'scope': scope})
            self.assertEqual(result.status_code, 200, result.content)
            return [row['subscription_id'] for row in result.json()['events']]
        self.assertEqual(ids('personal'), [personal.pk])
        self.assertEqual(ids('teams'), [])
        TeamMembership.objects.create(team=team, user=self.user, role='member')
        self.assertEqual(ids('teams'), [teamed.pk])
        Subscription.objects.filter(pk=teamed.pk).update(status='cancelled', cancellation_state='confirmed')
        self.assertEqual(ids('teams'), [])
