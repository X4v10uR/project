import csv
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import User
from subscriptions.models import Subscription, Transaction


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SubscriptionListPaginationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('page@example.test')
        self.other = User.objects.create_user('other@example.test')
        self.client.force_login(self.user)

    def create(self, name, **kwargs):
        fields = {
            'user': self.user, 'service_name': name, 'category': 'Other',
            'cost': '10', 'billing_cycle': 'monthly', 'start_date': date(2026, 1, 1),
            'notes': 'Only in the detail view',
        }
        return Subscription.objects.create(**{**fields, **kwargs})

    def test_page_bounds_card_payload_and_keeps_full_stats_and_authorized_details(self):
        for index in range(25):
            sub = self.create(f'Keep {index:02}')
        self.create('Unfiltered')
        private = self.create('Keep private', user=self.other)
        Transaction.objects.create(subscription=sub, user=self.user, amount='10',
                                   service_name_snapshot=sub.service_name, charged_for_date=date(2026, 1, 1))
        path = '/api/subscriptions/'
        with patch('subscriptions.list_context._build_subscription_drawer_data') as drawer:
            first = self.client.get(path, {'page': '1', 'q': 'Keep', 'sort': 'service_name'}).json()
            last = self.client.get(path, {'page': '2', 'q': 'Keep', 'sort': 'service_name'}).json()
            drawer.assert_not_called()
        self.assertEqual(first['pagination'], {'page': 1, 'pages': 2, 'count': 25, 'start': 1, 'end': 24})
        self.assertEqual(last['pagination'], {'page': 2, 'pages': 2, 'count': 25, 'start': 25, 'end': 25})
        self.assertEqual(len(first['subscriptions']), 24)
        self.assertEqual([row['id'] for row in last['subscriptions']], [sub.pk])
        self.assertEqual(first['stats']['total'], 26)
        self.assertEqual(first['stats']['monthly_spend_display'], '$260.00')
        self.assertEqual(first['stats'], last['stats'])
        self.assertEqual(first['burn_metrics']['tracked_count'], 26)
        self.assertNotIn('details', first)
        self.assertNotIn('notes', last['subscriptions'][0])
        self.assertNotIn('participants', last['subscriptions'][0])
        self.assertNotIn('card_last4', last['subscriptions'][0])
        raw = self.client.get(f'{path}{sub.pk}/').json()
        self.assertEqual(raw['notes'], 'Only in the detail view')
        self.assertEqual(raw['details']['history'][0]['amount_display'], '$10.00')
        self.assertEqual(self.client.get(f'{path}{private.pk}/').status_code, 404)
        unpaginated = self.client.get(path, {'q': 'Keep', 'sort': 'service_name'}).json()
        self.assertEqual(len(unpaginated['subscriptions']), 25)
        self.assertIn(str(sub.pk), unpaginated['details'])
        export = self.client.get(path + 'export/csv/', {'page': '2', 'q': 'Keep', 'sort': 'service_name'})
        self.assertEqual([r['Service Name'] for r in csv.DictReader(StringIO(export.content.decode()))],
                         [f'Keep {i:02}' for i in range(25)])

    def test_unknown_page_falls_back_and_out_of_range_page_clamps(self):
        self.create('Example')
        for page in ('oops', '', '-1', '999'):
            result = self.client.get('/api/subscriptions/', {'page': page}).json()
            self.assertEqual(result['pagination'], {'page': 1, 'pages': 1, 'count': 1, 'start': 1, 'end': 1})
        result = self.client.get('/api/subscriptions/', {'page': 2, 'q': 'Does not match'}).json()
        self.assertEqual(result['subscriptions'], [])
        self.assertEqual(result['pagination'], {'page': 1, 'pages': 1, 'count': 0, 'start': 0, 'end': 0})
