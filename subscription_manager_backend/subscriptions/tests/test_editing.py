from datetime import UTC, date, datetime
from unittest.mock import patch

from django.test import Client, TestCase

from accounts.models import User
from subscriptions.models import PriceChange, Subscription, Transaction


class SubscriptionEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('editing@example.test')
        self.client.force_login(self.user)
        self.second_tab = Client()
        self.second_tab.force_login(self.user)
        clock = patch('django.utils.timezone.now', return_value=datetime(2026, 11, 27, 12, tzinfo=UTC))
        clock.start()
        self.addCleanup(clock.stop)
        self.fields = {'service_name': 'Studio', 'category': 'Software', 'billing_cycle': 'monthly',
                       'start_date': '2026-11-27', 'currency': 'USD', 'cost': '30.00',
                       'status': 'active', 'split_type': 'equal'}
        response = self.client.post('/api/subscriptions/', self.fields, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        self.pk = response.json()['id']
        self.path = f'/api/subscriptions/{self.pk}/'

    def put(self, client, revision, **fields):
        return client.put(self.path, {**self.fields, **fields}, content_type='application/json',
                          HTTP_IF_MATCH=f'"{revision}"')

    def test_stale_rename_does_not_undo_newer_price(self):
        revision = self.second_tab.get(self.path).json()['edit_revision']
        self.assertEqual(self.put(self.client, revision, cost='40.00').status_code, 200)
        stale = self.put(self.second_tab, revision, service_name='Stale name')
        self.assertEqual(stale.status_code, 412)
        self.assertEqual(stale.json()['code'], 'stale_subscription')
        current = self.client.get(self.path).json()
        self.assertEqual((current['cost'], current['service_name']), ('40.00', 'Studio'))
        self.assertEqual(self.put(self.second_tab, current['edit_revision'],
                                  cost='40.00', service_name='New name').status_code, 200)
        self.assertEqual(PriceChange.objects.filter(subscription_id=self.pk).count(), 1)

    def test_price_history_cannot_change_currency(self):
        revision = self.client.get(self.path).json()['edit_revision']
        price = self.client.post(f'{self.path}prices/', {'cost': '40.00', 'effective_on': '2026-12-27'},
                                 content_type='application/json', HTTP_IF_MATCH=f'"{revision}"')
        self.assertEqual(price.status_code, 201, price.content)
        self.assertEqual(self.put(self.second_tab, revision, service_name='Old editor').status_code, 412)
        result = self.put(self.client, price.json()['edit_revision'], currency='GBP', cost='20.00')
        self.assertEqual(result.status_code, 400)
        self.assertIn('currency', result.json())
        current = self.client.get(self.path).json()
        self.assertEqual((current['currency'], current['next_payment']['amount']), ('USD', '40.00'))
        self.assertEqual(PriceChange.objects.filter(subscription_id=self.pk).count(), 1)

    def test_clean_currency_switch_does_not_relabel_already_recorded_charge(self):
        revision = self.client.get(self.path).json()['edit_revision']
        result = self.put(self.client, revision, currency='GBP', cost='20.00')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual((result.json()['currency'], result.json()['cost']), ('GBP', '20.00'))
        self.assertFalse(PriceChange.objects.filter(subscription_id=self.pk).exists())
        charge = Transaction.objects.get(subscription_id=self.pk, charged_for_date=date(2026, 11, 27))
        self.assertEqual((charge.currency, str(charge.amount)), ('USD', '30.00'))

    def test_currency_switch_requires_clearing_old_intro_offer(self):
        Subscription.objects.filter(pk=self.pk).update(introductory_cost='10.00', introductory_until=date(2026, 12, 5))
        revision = self.client.get(self.path).json()['edit_revision']
        result = self.put(self.client, revision, currency='GBP', cost='20.00',
                          introductory_cost='10.00', introductory_until='2026-12-05')
        self.assertEqual(result.status_code, 400)
        self.assertIn('currency', result.json())
        self.assertEqual(self.put(self.client, revision, currency='GBP', cost='20.00',
                                  introductory_cost='', introductory_until='').status_code, 200)
