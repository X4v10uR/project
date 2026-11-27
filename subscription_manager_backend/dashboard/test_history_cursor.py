from datetime import date, timedelta
from urllib.parse import urlsplit

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from subscriptions.models import Subscription, Transaction


class ChargeHistoryCursorTests(TestCase):
    def test_inserting_newest_charge_does_not_repeat_entries_across_next_page(self):
        user = User.objects.create_user('history-cursor@example.test')
        self.client.force_login(user)
        day = date(2026, 11, 27)

        def charge():
            return Transaction(user=user, service_name_snapshot='Example', amount='30.00',
                               currency='USD', charged_for_date=day)

        Transaction.objects.bulk_create([charge() for _ in range(51)])
        first = self.client.get('/api/dashboard/history/').json()
        new = charge()
        new.save()

        def follow(link):
            parsed = urlsplit(link)
            result = self.client.get(f'{parsed.path}?{parsed.query}')
            self.assertEqual(result.status_code, 200, result.content)
            return result.json()

        second = follow(first['next'])
        self.assertEqual(len(first['results']), 50)
        self.assertEqual(len(second['results']), 1)
        first_ids = [row['id'] for row in first['results']]
        second_ids = [row['id'] for row in second['results']]
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(len(set(first_ids + second_ids)), 51)
        self.assertEqual(second['count'], 52)
        self.assertEqual([row['id'] for row in follow(second['previous'])['results']], first_ids)
        self.assertEqual(self.client.get('/api/dashboard/history/').json()['results'][0]['id'], new.pk)
        self.assertEqual(self.client.get('/api/dashboard/history/?cursor_direction=older').status_code, 400)

    def test_dashboard_preview_keeps_totals_and_bounds_initial_collections(self):
        user = User.objects.create_user('dashboard-preview@example.test')
        self.client.force_login(user)
        today = timezone.localdate()
        day = today + timedelta(days=1)
        Subscription.objects.bulk_create([
            Subscription(user=user, service_name=f'Example {idx}', category='Other', currency='USD',
                         billing_cycle='monthly', cost='30.00', user_cost='30.00', start_date=day,
                         renewal_date=day, cancel_by_date=day)
            for idx in range(40)
        ])
        full = self.client.get('/api/dashboard/?currency=USD').json()
        preview = self.client.get('/api/dashboard/?currency=USD&preview=1').json()
        self.assertEqual((len(preview['active_subscriptions_panel']), len(preview['upcoming_bills']),
                          len(preview['needs_attention'])), (12, 25, 25))
        self.assertEqual((preview['total_active'], preview['upcoming_count'], preview['needs_attention_count']),
                         (40, 40, 40))
        self.assertEqual(preview['upcoming_week_count'], 40)
        self.assertEqual(len(preview['upcoming_week_days'][1]['items']), 3)
        self.assertEqual(preview['upcoming_week'], full['upcoming_week'])
        self.assertEqual(preview['yearly_spend'], full['yearly_spend'])
