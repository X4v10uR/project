from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import Team, TeamMembership, User
from subscriptions.models import ChargeShare, Subscription, Transaction

from .models import Connection, ImportedPayment


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ChargeDifferenceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('payer@example.com', 'example')
        self.other = User.objects.create_user('other@example.com', 'example')
        self.client.force_login(self.user)
        self.connection = Connection.objects.create(
            user=self.user, provider='statement', external_id='test', label='Checking', enabled=False,
        )
        self.day = date(2026, 11, 21)

    def subscription(self, user, team=None):
        return Subscription.objects.create(user=user, team=team, service_name='Studio', cost='12.00',
                                           currency='USD', start_date=self.day, billing_cycle='monthly')

    def charge(self, user, sub=None, team=None, amount='12.00'):
        return Transaction.objects.create(
            user=user, team=team, subscription=sub, service_name_snapshot='Studio',
            amount=amount, currency='USD', charged_for_date=self.day, shares_captured=True,
        )

    def payment(self, paid='13.44', **fields):
        return ImportedPayment.objects.create(
            connection=self.connection, remote_id=fields.pop('remote_id', 'txn-1'),
            merchant='Vendor', amount=paid, currency=fields.pop('currency', 'USD'),
            paid_on=self.day, **fields,
        )

    def match(self, payment, charge):
        return self.client.post(f'/api/finance/discoveries/{payment.pk}/', {
            'action': 'manual_match', 'charge': charge.pk,
        }, content_type='application/json')

    def dismiss(self, payment, delta):
        return self.client.post(f'/api/finance/charge-differences/{payment.pk}/dismiss/',
                                {'delta': delta}, content_type='application/json')

    def differences(self, scope='personal'):
        response = self.client.get('/api/dashboard/', {'scope': scope})
        self.assertEqual(response.status_code, 200)
        return [item for item in response.json()['needs_attention'] if item['kind'] == 'charge_difference']

    def test_matched_difference_dismisses_without_changing_price_or_ledger(self):
        sub = self.subscription(self.user)
        charge = self.charge(self.user, sub)
        payment = self.payment()
        self.assertEqual(self.differences(), [])
        self.assertEqual(self.match(payment, charge).status_code, 200)
        [alert] = self.differences()
        self.assertEqual(alert['amount'], '13.44')
        self.assertEqual(alert['difference'], {
            'expected': '12.00', 'delta': '1.44', 'payment_id': payment.pk,
            'price_url': f'/subscriptions/{sub.pk}/edit/#price-history',
        })
        self.assertEqual(self.dismiss(payment, '5.00').status_code, 400)
        self.assertEqual(self.dismiss(payment, '1.44').status_code, 200)
        self.assertEqual(self.differences(), [])
        charge.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(charge.amount, Decimal('12.00'))
        self.assertEqual(sub.cost, Decimal('12.00'))
        self.assertFalse(sub.price_changes.exists())
        self.assertEqual(charge.payment_status, 'paid')
        payment.refresh_from_db()
        self.assertFalse(payment.dismissed)
        self.assertEqual(payment.charge_id, charge.pk)
        ImportedPayment.objects.filter(pk=payment.pk).update(amount='11.00')
        [new_alert] = self.differences()
        self.assertEqual(new_alert['difference']['delta'], '-1.00')

    def test_ignores_equal_cross_currency_pending_removed_and_receipt_payments(self):
        charge = self.charge(self.user)
        charge.payment_status = 'paid'
        charge.save(update_fields=['payment_status'])
        row = self.payment('12.00', charge=charge)
        self.assertEqual(self.differences(), [])
        for fields in [
            {'amount': '13.44', 'currency': 'EUR'}, {'currency': 'USD', 'pending': True},
            {'pending': False, 'removed': True}, {'removed': False, 'dismissed': True},
        ]:
            ImportedPayment.objects.filter(pk=row.pk).update(**fields)
            self.assertEqual(self.differences(), [])
            self.assertEqual(self.dismiss(row, '1.44').status_code, 404)
        ImportedPayment.objects.filter(pk=row.pk).update(dismissed=False)
        Connection.objects.filter(pk=self.connection.pk).update(provider='gmail')
        self.assertEqual(self.differences(), [])

    def test_team_full_bill_uses_frozen_shares_and_bank_amount_stays_private(self):
        team = Team.objects.create(name='Studio team', created_by=self.other)
        TeamMembership.objects.get_or_create(user=self.other, team=team, defaults={'role': 'owner'})
        membership = TeamMembership.objects.create(user=self.user, team=team, role='accountant')
        sub = self.subscription(self.other, team)
        charge = self.charge(self.other, sub, team, amount='6.00')
        ChargeShare.objects.create(charge=charge, amount='6.00', name='Second share')
        payment = self.payment()
        self.assertEqual(self.match(payment, charge).status_code, 200)
        self.assertEqual(self.differences(), [])
        [alert] = self.differences('teams')
        self.assertEqual(alert['difference']['expected'], '12.00')
        self.assertEqual(alert['difference']['delta'], '1.44')
        self.assertIsNone(alert['difference']['price_url'])
        self.client.force_login(self.other)
        self.assertEqual(self.differences('teams'), [])
        self.assertEqual(self.dismiss(payment, '1.44').status_code, 404)
        self.client.force_login(self.user)
        membership.role = 'viewer'
        membership.save(update_fields=['role'])
        self.assertEqual(self.differences('teams'), [])
        self.assertEqual(self.dismiss(payment, '1.44').status_code, 404)

        membership.role = 'owner'
        membership.save(update_fields=['role'])
        [owner_alert] = self.differences('teams')
        self.assertEqual(owner_alert['difference']['price_url'], f'/subscriptions/{sub.pk}/edit/#price-history')
        self.assertEqual(self.dismiss(payment, '1.44').status_code, 200)

    def test_incomplete_legacy_split_does_not_raise_a_false_difference(self):
        sub = self.subscription(self.user)
        Subscription.objects.filter(pk=sub.pk).update(is_shared=True)
        charge = self.charge(self.user, sub, amount='6.00')
        Transaction.objects.filter(pk=charge.pk).update(shares_captured=False)
        payment = self.payment('12.00')
        self.assertEqual(self.match(payment, charge).status_code, 200)
        self.assertEqual(self.differences(), [])
