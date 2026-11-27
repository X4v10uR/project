import io
import json
import zipfile
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from accounts.models import Team, TeamMembership, User
from subscriptions.models import Subscription, Transaction
from .backup import build_archive, restore_archive
from .models import Connection, ImportedPayment


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StatementPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('payer@example.com', 'example')
        self.other = User.objects.create_user('other@example.com', 'example')
        self.client.force_login(self.user)

    def upload(self, content, mode='preview', **options):
        return self.client.post('/api/finance/statements/import/', {
            'file': SimpleUploadedFile('statement.csv', content.encode('utf-8-sig')),
            'mode': mode, **options})

    def test_preview_mapping_duplicate_detection_and_atomic_confirmation(self):
        csv = ('Posted;Shop;Sum;ID\n21/11/2026;Cinema;-12.00;a\n'
               '21/11/2026;Cinema;-12.00;a\n21/11/2026;Cinema;-12.00;b\n21/11/2026;Refund;3.00;c\n')
        response = self.upload(csv)
        self.assertEqual(response.json()['headers'], ['Posted', 'Shop', 'Sum', 'ID'])
        self.assertEqual(response.json()['rows'], [])
        options = dict(column_date='Posted', column_merchant='Shop', column_amount='Sum',
                       date_format='dmy', debits='negative', account='Checking')
        preview = self.upload(csv, **options).json()
        self.assertEqual([row['status'] for row in preview['rows']], ['ready', 'duplicate', 'ready', 'skipped'])
        self.assertFalse(Connection.objects.exists())
        self.assertEqual(self.upload(csv + 'oops;Invalid;-9.00;z\n', 'confirm', **options).status_code, 400)
        self.assertFalse(ImportedPayment.objects.exists())
        self.assertEqual(self.upload(csv, 'confirm', **options).json()['imported'], 2)
        second = self.upload(csv, 'confirm', **dict(options, account='checking')).json()
        self.assertEqual((second['duplicates'], second['imported']), (3, 0))
        self.assertFalse(Connection.objects.get().enabled)
        self.assertEqual(ImportedPayment.objects.count(), 2)

    def test_personal_match_allows_different_amount_and_merchant(self):
        self.upload('date,merchant,amount\n2026-11-21,Vendor LLC,13.44\n', 'confirm')
        payment = ImportedPayment.objects.get()
        charge = Transaction.objects.create(user=self.user, amount='12.00', currency='USD',
            service_name_snapshot='Streaming', charged_for_date=date(2026, 10, 30))
        path = f'/api/finance/discoveries/{payment.pk}/'
        def match(action):
            return self.client.post(path, {'action': action, 'charge': charge.pk}, content_type='application/json')
        self.assertEqual(match('match').status_code, 400)
        self.assertEqual(match('manual_match').status_code, 200)
        self.assertEqual(match('manual_match').status_code, 400)
        charge.refresh_from_db()
        self.assertEqual(str(charge.amount), '12.00')
        self.assertEqual(charge.payment_status, 'paid')
        self.assertEqual(ImportedPayment.objects.get().charge_id, charge.pk)

    def test_manual_options_distinguish_provider_total_payer_share_and_legacy_unknown(self):
        self.upload('date,merchant,amount\n2026-11-21,Vendor LLC,85.00\n', 'confirm')
        payment = ImportedPayment.objects.get()
        shared = Subscription.objects.create(user=self.user, service_name='Shared', cost='85.00',
            is_shared=True, start_date=date(2026, 10, 21), billing_cycle='monthly')
        captured = Transaction.objects.create(user=self.user, subscription=shared, amount='25.00',
            service_name_snapshot='Shared', charged_for_date=date(2026, 11, 21), shares_captured=True)
        captured.shares.create(name='Other', amount='60.00', reimbursed=True, repaid_amount='60.00')
        legacy = Transaction.objects.create(user=self.user, subscription=shared, amount='25.00',
            service_name_snapshot='Shared', charged_for_date=date(2026, 10, 21))
        solo = Transaction.objects.create(user=self.user, amount='85.00',
            service_name_snapshot='Solo', charged_for_date=date(2026, 11, 21))
        path = f'/api/finance/discoveries/{payment.pk}/'
        options = {row['id']: row for row in self.client.get(path + 'charges/').json()['charges']}
        self.assertEqual((options[captured.pk]['expected_provider_amount'], options[captured.pk]['payer_share']),
                         ('85.00', '25.00'))
        self.assertEqual((options[legacy.pk]['expected_provider_amount'], options[legacy.pk]['payer_share']),
                         (None, '25.00'))
        self.assertEqual((options[solo.pk]['expected_provider_amount'], options[solo.pk]['payer_share']),
                         ('85.00', None))
        self.assertEqual(self.client.post(path, {'action': 'manual_match', 'charge': captured.pk},
                                          content_type='application/json').status_code, 200)
        captured.refresh_from_db()
        self.assertEqual(str(captured.amount), '25.00')
        self.assertEqual(captured.payment_status, 'paid')
        self.assertEqual(str(captured.shares.get().amount), '60.00')

    def test_conflicting_transaction_references_are_reported_before_import(self):
        header = 'date,merchant,amount,reference\n'
        old = '2026-09-15,Cinema,13.50,A1\n'
        changed = '2026-09-15,Cinema,35.10,A1\n'
        new = '2026-09-16,Books,5,B1\n'
        preview = self.upload(header + old + changed).json()
        self.assertEqual(preview['errors'], 1)
        self.assertEqual(self.upload(header + old, 'confirm').json()['imported'], 1)
        self.assertEqual(self.upload(header + changed + new, 'confirm').status_code, 400)
        self.assertEqual(ImportedPayment.objects.count(), 1)

    def test_separate_debit_and_credit_columns_skip_deposits(self):
        statement = ('date,merchant,debit,credit\n2026-09-15,Cinema,12.50,\n'
                     '2026-09-16,Deposit,,"1,000.00"\n')
        preview = self.upload(statement).json()
        self.assertEqual([row['status'] for row in preview['rows']], ['ready', 'skipped'])
        self.assertEqual(self.upload(statement, 'confirm').json()['imported'], 1)
        self.assertEqual(self.upload(statement + '2026-09-17,Missing,,\n').json()['errors'], 1)

    def test_reimport_recognises_an_account_from_a_portable_restore(self):
        statement = 'date,merchant,amount\n2026-09-15,Cinema,13.50\n'
        self.upload(statement, 'confirm', account='Checking')
        with zipfile.ZipFile(io.BytesIO(build_archive(self.user))) as archive:
            restore_archive(self.other, archive, json.loads(archive.read('subly.json')))
        self.client.force_login(self.other)
        counts = self.upload(statement, 'confirm', account='CHECKING').json()
        self.assertEqual((counts['duplicates'], counts['imported']), (1, 0))
        self.assertEqual(self.upload(statement, 'confirm', account='Savings').json()['imported'], 1)

    def test_manually_matched_payments_do_not_suggest_a_duplicate_subscription(self):
        self.upload('date,merchant,amount\n2026-09-15,Vendor LLC,10\n2026-10-15,Vendor LLC,10\n', 'confirm')
        url = '/api/finance/discoveries/'
        self.assertEqual(len(self.client.get(url).json()['candidates']), 1)
        row = ImportedPayment.objects.earliest('paid_on')
        charge = Transaction.objects.create(user=self.user, amount='10.00', currency='USD',
            service_name_snapshot='Studio', charged_for_date=row.paid_on)
        self.assertEqual(self.client.post(f'{url}{row.pk}/', {'action': 'manual_match', 'charge': charge.pk},
                                          content_type='application/json').status_code, 200)
        discoveries = self.client.get(url).json()
        self.assertEqual(discoveries['candidates'], [])
        self.assertEqual(len(discoveries['payments']), 2)

    def test_team_match_permissions_are_rechecked_at_confirmation_and_export(self):
        self.upload('date,merchant,amount\n2026-11-21,Books,10\n', 'confirm')
        payment = ImportedPayment.objects.get()
        team = Team.objects.create(name='Library', created_by=self.other)
        membership = TeamMembership.objects.create(user=self.user, team=team, role='accountant')
        charge = Transaction.objects.create(team=team, user=self.other, amount='10', currency='USD',
            service_name_snapshot='Reader', charged_for_date=date(2026, 11, 21))
        path = f'/api/finance/discoveries/{payment.pk}/'
        def candidates():
            return self.client.get(path + 'charges/?q=Library').json()['charges']
        def match():
            return self.client.post(path, {'action': 'manual_match', 'charge': charge.pk}, content_type='application/json')
        self.assertEqual([option['id'] for option in candidates()], [charge.pk])
        membership.role = 'viewer'
        membership.save()
        self.assertEqual(candidates(), [])
        self.assertEqual(match().status_code, 404)
        membership.role = 'accountant'
        membership.save()
        self.assertEqual(match().status_code, 200)
        with zipfile.ZipFile(io.BytesIO(build_archive(self.user))) as archive:
            backup = json.loads(archive.read('subly.json'))
        self.assertEqual(backup['charges'], [])
        self.assertIsNone(backup['imports'][0]['charge_id'])

    def test_foreign_or_refunded_charges_and_currency_mismatches_are_excluded(self):
        self.upload('date,merchant,amount\n2026-11-21,Merchant,10\n', 'confirm')
        payment = ImportedPayment.objects.get()
        path = f'/api/finance/discoveries/{payment.pk}/'
        for owner, currency, status in [(self.other, 'USD', 'scheduled'), (self.user, 'EUR', 'paid'), (self.user, 'USD', 'refunded')]:
            charge = Transaction.objects.create(user=owner, amount='10', currency=currency, payment_status=status,
                service_name_snapshot='Store', charged_for_date=date(2026, 11, 21))
            result = self.client.post(path, {'action': 'manual_match', 'charge': charge.pk}, content_type='application/json')
            self.assertIn(result.status_code, (400, 404))
        self.assertEqual(self.client.get(path + 'charges/').json()['charges'], [])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(path + 'charges/').status_code, 404)
