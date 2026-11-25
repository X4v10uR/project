import io
import json
import tempfile
import time
import zipfile
from datetime import datetime, date, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, Mock
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import User, TeamMembership
from accounts.team_workflows import create_team, delete_user_account
from dashboard.models import BalanceAdjustment
from subscriptions.models import Subscription, Transaction, PriceChange, ChargeShare, Repayment, InAppNotification
from subscriptions.notifications import create_notification
from .models import Receipt, SpendingBudget, ExchangeRate, NotificationPreference, NotificationDelivery, PushSubscription, Connection, ImportedPayment, Activity
from .models import ScheduledJobStatus
from .backup import build_archive
from .connections import encrypt_tokens, tokens_for, sync_plaid, sync_gmail
from .delivery import deliver_queued, send_digests, route_notification, quiet_until, validate_push


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class FinanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('finance@example.test', 'Password-example-42')
        self.other = User.objects.create_user('other@example.test', 'Password-example-42')
        self.client.force_login(self.user)
        session = self.client.session
        session['reauthenticated_at'] = time.time()
        session.save()
        self.today = timezone.localdate()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = override_settings(PRIVATE_MEDIA_ROOT=self.temp.name)
        self.storage.enable()
        self.addCleanup(self.storage.disable)
        field = Receipt._meta.get_field('file')
        original = field.storage
        field.storage = FileSystemStorage(location=self.temp.name)
        self.addCleanup(setattr, field, 'storage', original)

    def sub(self, **fields):
        return Subscription.objects.create(**{'user': self.user, 'service_name': 'Studio', 'category': 'Software', 'billing_cycle': 'monthly', 'cost': '30.00', 'start_date': self.today, **fields})

    def charge(self, sub, **fields):
        return Transaction.objects.create(**{'user': sub.user, 'subscription': sub, 'service_name_snapshot': sub.service_name, 'amount': sub.cost, 'currency': sub.currency, 'charged_for_date': self.today, **fields})

    def post(self, path, data=None):
        return self.client.post('/api/finance/' + path, data or {}, content_type='application/json')

    def pdf(self, text='Invoice 2026-11-19 Total: USD 30.00'):
        from reportlab.pdfgen import canvas
        output = io.BytesIO()
        pdf = canvas.Canvas(output)
        pdf.drawString(80, 750, text)
        pdf.save()
        return SimpleUploadedFile('invoice.pdf', output.getvalue(), 'application/pdf')

    def test_receipts_extract_pdf_and_are_private(self):
        sub = self.sub()
        result = self.client.post('/api/finance/receipts/', {'file': self.pdf(), 'subscription': sub.pk})
        self.assertEqual(result.status_code, 201, result.content)
        row = result.json()
        self.assertEqual(row['amount'], '30.00')
        self.assertEqual(row['currency'], 'USD')
        receipt = Receipt.objects.get()
        self.assertNotIn('/media/', row['download_url'])
        response = self.client.get(row['download_url'], HTTP_ACCEPT='application/pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        response.close()
        self.assertEqual(self.client.get(row['download_url'], HTTP_ACCEPT='image/png').status_code, 406)
        self.assertEqual(self.client.delete(row['download_url']).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(row['download_url']).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/finance/receipts/{receipt.pk}/', {'note': 'x'}, content_type='application/json').status_code, 404)

    def test_image_receipts_download_in_the_original_format(self):
        from PIL import Image

        for image_format, mime in [('PNG', 'image/png'), ('JPEG', 'image/jpeg')]:
            with self.subTest(image_format=image_format):
                buffer = io.BytesIO()
                Image.new('RGB', (2, 2)).save(buffer, format=image_format)
                original = buffer.getvalue()
                file = SimpleUploadedFile('receipt.' + image_format.lower(), original, content_type=mime)
                upload = self.client.post('/api/finance/receipts/', {'file': file})
                self.assertEqual(upload.status_code, 201, upload.content)
                response = self.client.get(upload.json()['download_url'], HTTP_ACCEPT=mime)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], mime)
                self.assertEqual(b''.join(response.streaming_content), original)

    def test_receipt_extracts_total_after_subtotal(self):
        for label in ('Subtotal', 'Sub-total', 'Sub Total'):
            with self.subTest(label=label):
                file = self.pdf(f'{label}: USD 20.00    Tax: USD 2.00    Total: USD 22.00')
                response = self.client.post('/api/finance/receipts/', {'file': file})
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.json()['amount'], '22.00')

    def test_missing_receipt_file_returns_404_and_prevents_incomplete_backup(self):
        self.client.post('/api/finance/receipts/', {'file': self.pdf()})
        row = Receipt.objects.get()
        row.file.storage.delete(row.file.name)
        for name in (row.file.name, ''):
            with self.subTest(name=name):
                Receipt.objects.filter(pk=row.pk).update(file=name)
                self.assertEqual(self.client.get(f'/api/finance/receipts/{row.pk}/file/').status_code, 404)
                self.assertEqual(self.post('backup/export/').status_code, 400)

    def test_receipt_file_deletion_follows_transaction_commit(self):
        self.client.post('/api/finance/receipts/', {'file': self.pdf()})
        row = Receipt.objects.get()
        url = f'/api/finance/receipts/{row.pk}/'
        with transaction.atomic():
            self.assertEqual(self.client.delete(url).status_code, 204)
            transaction.set_rollback(True)
        self.assertTrue(row.file.storage.exists(row.file.name))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(row.file.storage.exists(row.file.name))

    def test_deleting_former_member_preserves_team_receipt_and_activity(self):
        team = create_team(name='Surviving team', user=self.other)
        membership = TeamMembership.objects.create(team=team, user=self.user, role=TeamMembership.ROLE_ACCOUNTANT)
        sub = self.sub(team=team, user=self.other)
        upload = self.client.post('/api/finance/receipts/', {'file': self.pdf(), 'subscription': sub.pk})
        self.assertEqual(upload.status_code, 201, upload.content)
        receipt = Receipt.objects.get(pk=upload.json()['id'])
        activity = Activity.objects.create(user=self.user, owner=self.user, team=team, action='receipt.uploaded')
        personal = Receipt.objects.create(user=self.user, file=self.pdf(), filename='personal.pdf')
        membership.delete()

        with self.captureOnCommitCallbacks(execute=True):
            delete_user_account(self.user)
        receipt.refresh_from_db()
        activity.refresh_from_db()
        self.assertEqual(receipt.user_id, self.other.pk)
        self.assertEqual(activity.owner_id, self.other.pk)
        self.assertIsNone(activity.user_id)
        self.assertFalse(personal.file.storage.exists(personal.file.name))
        self.client.force_login(self.other)
        response = self.client.get(upload.json()['download_url'], HTTP_ACCEPT='application/pdf')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(b''.join(response.streaming_content).startswith(b'%PDF-'))

    def test_receipts_reject_disguised_html_and_foreign_subscription(self):
        result = self.client.post('/api/finance/receipts/', {'file': SimpleUploadedFile('invoice.pdf', b'<script>alert(1)</script>', 'application/pdf')})
        self.assertEqual(result.status_code, 400)
        sub = self.sub(user=self.other)
        self.assertEqual(self.client.post('/api/finance/receipts/', {'file': self.pdf(), 'subscription': sub.pk}).status_code, 404)

    def test_category_and_team_budgets_use_correct_amount_and_threshold(self):
        self.sub()
        self.sub(service_name='Music', category='Music', cost='100')
        with self.captureOnCommitCallbacks(execute=True):
            result = self.post('budgets/', {'currency': 'usd', 'category': 'Software', 'monthly_limit': '35', 'warning_percent': 80})
        self.assertEqual(result.status_code, 201, result.content)
        self.assertEqual(result.json()['spend'], '30.00')
        self.assertEqual(InAppNotification.objects.filter(event_type='budget.warning').count(), 1)
        self.post('budgets/', {'currency': 'USD', 'category': 'Software', 'monthly_limit': '35', 'warning_percent': 80})
        self.assertEqual(InAppNotification.objects.filter(event_type='budget.warning').count(), 1)
        team = create_team(name='Team', user=self.other)
        TeamMembership.objects.create(team=team, user=self.user, role='viewer')
        self.assertEqual(self.post('budgets/', {'team_id': team.pk, 'currency': 'USD', 'monthly_limit': '20'}).status_code, 403)

    def test_conversion_does_not_hide_missing_currencies(self):
        self.sub(currency='USD', cost=30)
        self.sub(currency='EUR', cost=20)
        data = self.client.get('/api/finance/conversion/?base=USD').json()
        self.assertFalse(data['complete'])
        self.assertEqual(data['missing'], ['EUR'])
        ExchangeRate.objects.create(base='USD', quote='EUR', rate=Decimal('.8'), as_of=self.today - timedelta(days=9))
        data = self.client.get('/api/finance/conversion/?base=USD').json()
        self.assertEqual(data['monthly_total'], '55.00')
        self.assertTrue(data['rates'][0]['stale'])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/finance/conversion/?base=USD').json()['monthly_total'], '0.00')

    @patch('finance.views.requests.get')
    def test_refresh_rates_persists_reference_date(self, get):
        self.sub(currency='EUR')
        get.return_value.json.return_value = [{'base': 'USD', 'quote': 'EUR', 'rate': .9, 'date': str(self.today)}]
        result = self.post('conversion/?base=USD')
        self.assertTrue(result.json()['complete'])
        self.assertEqual(ExchangeRate.objects.get().as_of, self.today)

    def test_report_filters_and_csv_formula_escape_and_pdf(self):
        row = self.charge(self.sub(service_name='=FORMULA()'))
        self.charge(self.sub(user=self.other, service_name='Hidden'))
        result = self.client.get('/api/finance/reports/?filetype=csv', HTTP_ACCEPT='text/csv')
        self.assertEqual(result.status_code, 200)
        self.assertIn("'=FORMULA()", result.content.decode('utf-8-sig'))
        self.assertNotIn('Hidden', result.content.decode('utf-8-sig'))
        result = self.client.get('/api/finance/reports/', HTTP_ACCEPT='application/pdf')
        self.assertEqual(result['Content-Type'], 'application/pdf')
        self.assertTrue(result.content.startswith(b'%PDF-'))
        self.assertEqual(self.client.get('/api/finance/reports/?filetype=pdf', HTTP_ACCEPT='text/csv').status_code, 406)
        self.assertNotIn('FORMULA', self.client.get('/api/finance/reports/?status=paid').content.decode('utf-8-sig'))

    def test_live_calendar_updates_and_can_be_revoked(self):
        sub = self.sub()
        result = self.post('calendar/feeds/', {'scope': 'personal'})
        url = result.json()['url'].split(settings.SITE_URL)[-1]
        self.client.logout()
        response = self.client.get(url, HTTP_ACCEPT='text/calendar')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'].split(';')[0], 'text/calendar')
        self.assertIn('Studio', response.content.decode())
        sub.service_name = 'Updated Studio'
        sub.save()
        self.assertIn('Updated Studio', self.client.get(url).content.decode())
        self.client.force_login(self.user)
        result = self.client.delete('/api/finance/calendar/feeds/', {'id': result.json()['id']}, content_type='application/json')
        self.assertEqual(result.status_code, 204)
        revoked = self.client.get(url, HTTP_ACCEPT='text/calendar')
        self.assertEqual(revoked.status_code, 404)
        self.assertIn('detail', revoked.json())

    def test_backup_roundtrip_retains_financial_history_and_receipt(self):
        sub = self.sub()
        sub.set_account_password('never-export-this')
        sub.save()
        PriceChange.objects.create(subscription=sub, previous_cost=25, cost=30, effective_on=self.today)
        charge = self.charge(sub, payment_status='paid')
        share = ChargeShare.objects.create(charge=charge, name='Alex', amount=10, repaid_amount=4)
        Repayment.objects.create(share=share, amount=4, recorded_by=self.user, note='Partial')
        result = self.client.post('/api/finance/receipts/', {'file': self.pdf(), 'subscription': sub.pk, 'charge': charge.pk})
        self.assertEqual(result.status_code, 201)
        exported = self.client.post('/api/finance/backup/export/', HTTP_ACCEPT='application/zip')
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported['Content-Type'], 'application/zip')
        content = exported.content
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertNotIn('never-export-this', archive.read('subly.json').decode())
            self.assertIn('receipts/' + str(Receipt.objects.get().pk), archive.namelist())
        self.client.force_login(self.other)
        session = self.client.session; session['reauthenticated_at'] = time.time(); session.save()
        result = self.client.post('/api/finance/backup/restore/', {'file': SimpleUploadedFile('backup.zip', content), 'confirm': 'RESTORE'})
        self.assertEqual(result.status_code, 200, result.content)
        copied = Subscription.objects.get(user=self.other)
        self.assertEqual(copied.price_changes.count(), 1)
        self.assertFalse(copied.account_password)
        copied_charge = copied.transactions.get()
        self.assertEqual(copied_charge.payment_status, 'paid')
        self.assertEqual(copied_charge.shares.get().repayments.get().amount, Decimal('4'))
        self.assertEqual(Receipt.objects.filter(user=self.other).count(), 1)

    def test_backup_invalid_reference_rolls_back_all_changes(self):
        self.sub()
        content = build_archive(self.user)
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            data = json.loads(z.read('subly.json'))
        data['subscriptions'][0]['team_id'] = 999999
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('subly.json', json.dumps(data))
        count = Subscription.objects.count()
        result = self.client.post('/api/finance/backup/restore/', {'file': SimpleUploadedFile('backup.zip', output.getvalue()), 'confirm': 'RESTORE'})
        self.assertEqual(result.status_code, 400)
        self.assertEqual(Subscription.objects.count(), count)

    def test_backup_restores_charge_for_deleted_subscription_with_receipt(self):
        sub = self.sub()
        charge = self.charge(sub, payment_status='paid')
        self.client.post('/api/finance/receipts/', {'file': self.pdf(), 'charge': charge.pk})
        sub.delete()
        result = self.client.post('/api/finance/backup/restore/', {
            'file': SimpleUploadedFile('backup.zip', build_archive(self.user)), 'confirm': 'RESTORE',
        })
        self.assertEqual(result.status_code, 200, result.content)
        copied = Transaction.objects.exclude(pk=charge.pk).get()
        self.assertIsNone(copied.subscription_id)
        self.assertEqual(copied.payment_status, 'paid')
        self.assertTrue(Receipt.objects.filter(charge=copied, subscription=None).exists())

    def test_invalid_receipt_timestamp_leaves_no_restored_files(self):
        pdf = self.pdf()
        content = pdf.read()
        data = {'version': 1, 'receipts': [
            {'id': 1, 'filename': pdf.name}, {'id': 2, 'filename': pdf.name, 'created_at': 'unknown'},
        ]}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('subly.json', json.dumps(data))
            for row in data['receipts']:
                archive.writestr(f'receipts/{row["id"]}', content)
        result = self.client.post('/api/finance/backup/restore/', {
            'file': SimpleUploadedFile('backup.zip', output.getvalue()), 'confirm': 'RESTORE',
        })
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Receipt.objects.exists())
        self.assertFalse(any(path.is_file() for path in Path(self.temp.name).rglob('*')))

    def test_restoring_existing_limits_keeps_one_editable_budget_and_counts_balances(self):
        budget = SpendingBudget.objects.create(user=self.user, currency='USD', monthly_limit=50)
        adjustment = BalanceAdjustment.objects.create(user=self.user, currency='USD', monthly_limit=0, amount=-10)
        content = build_archive(self.user)
        SpendingBudget.objects.filter(pk=budget.pk).update(monthly_limit=25)
        BalanceAdjustment.objects.filter(pk=adjustment.pk).update(amount=20)
        result = self.client.post('/api/finance/backup/restore/', {
            'file': SimpleUploadedFile('backup.zip', content), 'confirm': 'RESTORE',
        })
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['restored']['balances'], 1)
        adjustment.refresh_from_db()
        self.assertEqual(adjustment.amount, Decimal('-10'))
        self.assertEqual(SpendingBudget.objects.get().monthly_limit, Decimal('50'))
        edited = self.post('budgets/', {'currency': 'USD', 'monthly_limit': '75'})
        self.assertEqual(edited.status_code, 201)
        self.assertEqual(edited.json()['id'], budget.pk)

    def test_backup_restores_activity_without_change_details(self):
        sub = self.sub()
        result = self.client.delete(f'/api/subscriptions/{sub.pk}/')
        self.assertEqual(result.status_code, 204)
        self.assertEqual(Activity.objects.get().changes, {})
        content = build_archive(self.user)
        result = self.client.post('/api/finance/backup/restore/', {
            'file': SimpleUploadedFile('backup.zip', content), 'confirm': 'RESTORE',
        })
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(Activity.objects.filter(action='subscription.deleted', changes={}).count(), 2)

    def test_accountant_can_record_payments_but_cannot_reveal_credentials(self):
        team = create_team(name='Finance', user=self.other)
        member = TeamMembership.objects.create(team=team, user=self.user, role='accountant')
        sub = self.sub(user=self.other, team=team, account_password='secret')
        charge = self.charge(sub)
        url = f'/api/dashboard/history/{charge.pk}/payment/'
        self.assertEqual(self.client.patch(url, {'payment_status': 'paid'}, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.post(f'/api/accounts/teams/{team.pk}/subscriptions/{sub.pk}/password/').status_code, 403)
        self.assertEqual(self.client.post(f'/accounts/teams/{team.pk}/subscriptions/{sub.pk}/password/').status_code, 403)
        member.role = 'viewer'; member.save()
        self.assertEqual(self.client.patch(url, {'payment_status': 'failed'}, content_type='application/json').status_code, 404)
        self.assertEqual(self.client.post('/api/subscriptions/', {'team_id': team.pk, 'service_name': 'New', 'cost': '5', 'billing_cycle': 'monthly', 'start_date': str(self.today)}, content_type='application/json').status_code, 400)

    def test_owner_cannot_remove_last_owner_role(self):
        team = create_team(name='Owned', user=self.user)
        member = TeamMembership.objects.get(team=team, user=self.user)
        result = self.client.patch(f'/api/accounts/teams/{team.pk}/members/{member.pk}/', {'role': 'viewer'}, content_type='application/json')
        self.assertEqual(result.status_code, 400)
        member.refresh_from_db(); self.assertEqual(member.role, 'owner')

    def test_activity_tracks_changes_without_passwords(self):
        result = self.client.post('/api/subscriptions/', {'service_name': 'Studio', 'cost': '9', 'billing_cycle': 'monthly', 'start_date': str(self.today), 'account_password': 'NeverInAudit'}, content_type='application/json')
        self.assertEqual(result.status_code, 201)
        result = self.client.get('/api/finance/activity/')
        self.assertIn('subscription.created', result.content.decode())
        self.assertNotIn('NeverInAudit', result.content.decode())
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/finance/activity/').json()['activity'], [])

    def test_connection_tokens_are_encrypted_and_never_serialized(self):
        row = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens=encrypt_tokens({'access_token': 'private-token'}))
        self.assertNotIn('private-token', row.encrypted_tokens)
        self.assertEqual(tokens_for(row)['access_token'], 'private-token')
        self.assertNotIn('private-token', self.client.get('/api/finance/connections/').content.decode())
        self.client.force_login(self.other)
        self.assertEqual(self.post(f'connections/{row.pk}/').status_code, 404)

    @patch('finance.connections.plaid')
    def test_plaid_sync_pagination_is_idempotent_and_removed_rows_are_retained(self, plaid):
        row = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens=encrypt_tokens({'access_token': 'token'}))
        payment = {'transaction_id': 'one', 'merchant_name': 'Studio', 'name': 'Studio', 'amount': 30, 'iso_currency_code': 'USD', 'date': str(self.today), 'pending': False}
        plaid.side_effect = [{'added': [payment], 'next_cursor': 'a', 'has_more': True}, {'added': [], 'next_cursor': 'b', 'has_more': False}]
        sync_plaid(row)
        self.assertEqual(ImportedPayment.objects.count(), 1)
        plaid.side_effect = None
        plaid.return_value = {'added': [payment], 'removed': [{'transaction_id': 'one'}], 'next_cursor': 'c', 'has_more': False}
        sync_plaid(row)
        self.assertEqual(ImportedPayment.objects.count(), 1)
        self.assertTrue(ImportedPayment.objects.get().removed)

    def test_discovery_uses_full_calendar_history_and_preserves_month_end(self):
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank')
        histories = {
            'Monthly': [date(2026, m, 1) for m in (1, 2, 3)],
            'Month end': [date(2026, 1, 31), date(2026, 2, 28)],
            'Four weeks': [date(2026, 1, 4) + timedelta(weeks=4 * i) for i in range(4)],
            'Irregular': [date(2026, 1, 1), date(2026, 2, 15), date(2026, 3, 15)],
        }
        for merchant, dates in histories.items():
            for day in dates:
                ImportedPayment.objects.create(connection=connection, remote_id=f'{merchant}-{day}', merchant=merchant,
                                               amount=20, currency='USD', paid_on=day)
        result = self.client.get('/api/finance/discoveries/').json()
        found = {row['service']: row for row in result['candidates']}
        self.assertEqual(set(found), {'Monthly', 'Month end', 'Four weeks'})
        for name, cycle, expected in [('Monthly', 'monthly', '2026-04-01'), ('Month end', 'monthly', '2026-03-31'),
                                      ('Four weeks', 'fourweekly', '2026-04-26')]:
            row = found[name]
            self.assertEqual((row['billing_cycle'], row['next_payment_date']), (cycle, expected))
            sub = Subscription(start_date=date.fromisoformat(row['start_date']), billing_cycle=cycle)
            self.assertEqual(sub.calculate_renewal_date(histories[name][-1] + timedelta(days=1)).isoformat(), expected)

    @patch('django.utils.timezone.localdate', return_value=date(2026, 1, 31))
    def test_accepting_early_payment_skips_paid_cycle_and_preserves_month_end(self, _today):
        from subscriptions.services import BillingService, NotificationService

        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='early')
        for day in (date(2025, 10, 31), date(2025, 11, 30), date(2025, 12, 31), date(2026, 1, 30)):
            ImportedPayment.objects.create(connection=connection, merchant='Studio', remote_id=str(day),
                                           amount=20, currency='USD', paid_on=day)
        candidate, = self.client.get('/api/finance/discoveries/').json()['candidates']
        self.assertEqual(candidate['paid_through'], '2026-01-31')
        self.assertEqual(candidate['next_payment_date'], '2026-02-28')
        response = self.client.post('/api/subscriptions/', {
            'service_name': candidate['service'], 'reminder_offsets': [3],
            **{k: candidate[k] for k in ('cost', 'currency', 'billing_cycle', 'start_date', 'paid_through')},
        }, content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['renewal_date'], candidate['next_payment_date'])
        sub = Subscription.objects.get(pk=response.json()['id'])
        self.assertFalse(sub.transactions.exists())
        self.assertEqual(BillingService.record_renewal_charges(date(2026, 1, 31))['created'], 0)
        def reminders(month, day):
            instant = datetime(2026, month, day, 10, tzinfo=dt_timezone.utc)
            return [s.renewal_date for s, _ in NotificationService.get_subscriptions_due_for_notification(now=instant)
                    if s.pk == sub.pk]
        self.assertEqual(reminders(1, 30), [])
        self.assertEqual(reminders(2, 26), [date(2026, 2, 28)])
        self.assertEqual(BillingService.record_renewal_charges(date(2026, 3, 31))['created'], 2)
        self.assertEqual(BillingService.record_renewal_charges(date(2026, 3, 31))['created'], 0)
        self.assertCountEqual(sub.transactions.values_list('charged_for_date', flat=True),
                              [date(2026, 2, 28), date(2026, 3, 31)])

    def test_older_pages_keep_filters_and_permissions_across_inserts(self):
        # Use one timestamp to exercise the secondary ordering by id.
        from urllib.parse import urlsplit
        def fetch_next(link):
            url = urlsplit(link)
            return self.client.get(url.path + '?' + url.query).json()

        for user, count, merchant in [(self.user, 52, 'Studio'), (self.other, 2, 'Studio'), (self.user, 1, 'Elsewhere')]:
            Receipt.objects.bulk_create([Receipt(user=user, merchant=merchant, issued_on=self.today, filename=f'{i}.pdf') for i in range(count)])
        Receipt.objects.create(user=self.user, merchant='Studio', issued_on=self.today - timedelta(days=1))
        Receipt.objects.update(created_at=timezone.now())
        url = f'/api/finance/receipts/?merchant=STUD&start={self.today}&end={self.today}'
        first = self.client.get(url).json()
        self.assertEqual(len(first['receipts']), 50)
        expected = [r['id'] for r in self.client.get(url + '&page=2').json()['receipts']]
        Receipt.objects.create(user=self.user, merchant='Studio', issued_on=self.today)
        Receipt.objects.filter(pk=first['receipts'][-1]['id']).delete()
        second = fetch_next(first['next'])
        self.assertEqual([r['id'] for r in second['receipts']], expected)
        self.assertEqual(len(expected), 2)
        self.assertIsNone(second['next'])
        self.assertEqual(self.client.get('/api/finance/receipts/?start=2026-06-01&end=2026-01-01').status_code, 400)
        Activity.objects.bulk_create([Activity(owner=self.user, service='Studio', action='review') for _ in range(52)])
        Activity.objects.create(owner=self.other, service='Private', action='review')
        first = self.client.get('/api/finance/activity/').json()
        second = fetch_next(first['next'])
        self.assertEqual(len({r['id'] for r in first['activity'] + second['activity']}), 52)
        self.assertIsNone(second['next'])
        self.assertTrue(all(r['service'] == 'Studio' for r in first['activity'] + second['activity']))

    def test_scheduler_records_partial_failure_and_preserves_last_success(self):
        from scheduler import run_scheduler
        self.assertEqual(run_scheduler(), 0)
        previous = ScheduledJobStatus.objects.get(job='finance_sync').last_succeeded_at
        Connection.objects.create(user=self.user, provider='plaid', external_id='item')
        from .connections import ProviderError
        with patch('finance.management.commands.sync_finance.sync_connection', side_effect=ProviderError('offline')):
            with self.assertLogs('scheduler', level='ERROR'):
                self.assertEqual(run_scheduler(), 1)
        status = ScheduledJobStatus.objects.get(job='finance_sync')
        self.assertFalse(status.succeeded)
        self.assertEqual(status.last_succeeded_at, previous)
        reminder = ScheduledJobStatus.objects.get(job='renewal_reminders')
        self.assertTrue(reminder.succeeded)
        self.assertGreaterEqual(reminder.last_succeeded_at, status.last_finished_at)
        before = list(ScheduledJobStatus.objects.order_by('pk').values())
        self.assertEqual(run_scheduler(dry_run=True), 0)
        self.assertEqual(list(ScheduledJobStatus.objects.order_by('pk').values()), before)

    def test_dashboard_attention_links_respect_scope_and_resolve(self):
        from subscriptions.models import TeamSubscriptionRequest
        team = create_team(name='Owned', user=self.user)
        TeamMembership.objects.create(team=team, user=self.other, role='member')
        nearest = self.sub(cancel_by_date=self.today + timedelta(days=1))
        self.sub(cancel_by_date=self.today + timedelta(days=3))
        self.sub(user=self.other, cancel_by_date=self.today)
        failed = self.charge(nearest, payment_status='failed')
        pending = TeamSubscriptionRequest.objects.create(team=team, requested_by=self.other, payload={'service_name': 'Team plan'})
        personal = self.client.get('/api/dashboard/').json()['needs_attention']
        self.assertEqual([r['kind'] for r in personal], ['payment', 'deadline', 'deadline'])
        self.assertIn(f'/{nearest.pk}/edit/', personal[1]['url'])
        query = personal[0]['url'].split('?')[1]
        self.assertEqual(self.client.get('/api/dashboard/history/?' + query).json()['results'][0]['id'], failed.pk)
        team_url = '/api/dashboard/?scope=teams'
        approval, = self.client.get(team_url).json()['needs_attention']
        self.assertTrue(approval['url'].endswith(f'#request-{pending.pk}'))
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(team_url).json()['needs_attention'], [])
        self.assertEqual(self.client.get('/api/dashboard/history/?' + query).json()['count'], 0)
        self.client.force_login(self.user)
        pending.status = 'approved'
        pending.save()
        self.assertEqual(self.client.get(team_url).json()['needs_attention'], [])

    def test_weekly_queue_uses_the_recipients_week_and_effective_prices(self):
        from finance.delivery import local_now
        today = local_now(self.user).date()
        trial = self.sub(trial_end_date=today + timedelta(days=6))
        self.sub(cancel_by_date=today + timedelta(days=7))
        sub = self.sub(introductory_cost='10.00', introductory_until=today + timedelta(days=2))
        PriceChange.objects.create(subscription=sub, cost='25.00', previous_cost='30.00', effective_on=today + timedelta(days=3))
        data = self.client.get('/api/dashboard/').json()
        self.assertFalse(data['show_get_started'])
        self.assertEqual([(item['kind'], item['amount']) for item in data['needs_attention']],
                         [('price', '30.00'), ('trial', '30.00')])
        self.assertIn(f'/{trial.pk}/edit/', data['needs_attention'][1]['url'])

    def test_matching_requires_exact_identity_amount_and_date(self):
        charge = self.charge(self.sub())
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens='x')
        payment = ImportedPayment.objects.create(connection=connection, remote_id='one', merchant='Studio', amount=30, currency='USD', paid_on=self.today)
        data = self.client.get('/api/finance/discoveries/').json()
        self.assertEqual(data['payments'][0]['matches'][0]['id'], charge.pk)
        self.assertEqual(self.post(f'discoveries/{payment.pk}/', {'action': 'match', 'charge': charge.pk}).status_code, 200)
        charge.refresh_from_db(); self.assertEqual(charge.payment_status, 'paid')
        self.assertEqual(self.post(f'discoveries/{payment.pk}/', {'action': 'match', 'charge': charge.pk}).status_code, 400)

    def test_payment_matches_distinguish_non_latin_merchants(self):
        first = self.charge(self.sub(service_name='東京'))
        self.charge(self.sub(service_name='大阪'))
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='bank')
        for index, merchant in enumerate(['東京', '大阪']):
            ImportedPayment.objects.create(connection=connection, remote_id=str(index), merchant=merchant,
                                           amount=30, currency='USD', paid_on=self.today - timedelta(days=7 * index))
        data = self.client.get('/api/finance/discoveries/').json()
        self.assertEqual(data['candidates'], [])
        self.assertEqual([row['id'] for row in data['payments'][0]['matches']], [first.pk])

    @patch('finance.connections.plaid')
    def test_plaid_correction_to_credit_withdraws_old_debit(self, plaid):
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='bank',
                                               encrypted_tokens=encrypt_tokens({'access_token': 'token'}))
        debit = {'transaction_id': 'one', 'name': 'Studio', 'amount': 30, 'iso_currency_code': 'USD', 'date': str(self.today)}
        plaid.side_effect = [
            {'added': [debit], 'next_cursor': 'a', 'has_more': False},
            {'modified': [{**debit, 'amount': -30}], 'next_cursor': 'b', 'has_more': False},
            {'modified': [debit], 'next_cursor': 'c', 'has_more': False},
        ]
        sync_plaid(connection)
        sync_plaid(connection)
        self.assertEqual(self.client.get('/api/finance/discoveries/').json()['payments'], [])
        sync_plaid(connection)
        self.assertFalse(ImportedPayment.objects.get().removed)

    def test_gmail_callback_checks_state_and_session_owner(self):
        self.assertEqual(self.client.get('/api/finance/connections/gmail/callback/?state=invalid&code=x').status_code, 400)

    @patch('finance.connections.provider_request')
    def test_gmail_captures_attachment_only_invoices_once(self, request):
        import base64
        connection = Connection.objects.create(user=self.user, provider='gmail', external_id='mail', label='Mail', encrypted_tokens=encrypt_tokens({'access_token': 'secret', 'expires_at': time.time() + 3600}))
        content = base64.urlsafe_b64encode(self.pdf().read()).decode()
        message = {'payload': {'headers': [{'name': 'From', 'value': 'Studio <studio@example.test>'}, {'name': 'Subject', 'value': 'Your invoice'}, {'name': 'Date', 'value': 'Thu, 19 Nov 2026 10:00:00 +0000'}],
            'parts': [{'filename': 'invoice.pdf', 'mimeType': 'application/pdf', 'body': {'data': content}}]}}
        request.side_effect = [{'messages': [{'id': 'message-one'}]}, message]
        sync_gmail(connection)
        self.assertEqual(Receipt.objects.get().amount, Decimal('30'))
        self.assertEqual(ImportedPayment.objects.get().amount, Decimal('30'))
        request.side_effect = [{'messages': [{'id': 'message-one'}]}]
        sync_gmail(connection)
        self.assertEqual(Receipt.objects.count(), 1)

    @patch('finance.connections.provider_request')
    def test_gmail_resumes_same_name_attachments_with_their_own_amounts_and_dates(self, request):
        import base64
        from .connections import ProviderError

        connection = Connection.objects.create(user=self.user, provider='gmail', external_id='mail',
            encrypted_tokens=encrypt_tokens({'access_token': 'token', 'expires_at': time.time() + 3600}))
        listing = {'messages': [{'id': 'two-invoices'}]}
        first = base64.urlsafe_b64encode(self.pdf('2026-10-10 Total: EUR 7.00').read()).decode()
        second = base64.urlsafe_b64encode(self.pdf('2026-10-12 Total: USD 9.00').read()).decode()
        message = {'payload': {'parts': [
            {'mimeType': 'text/plain', 'body': {'data': base64.urlsafe_b64encode(
                b'Invoice summary dated 2026-10-15. Total: USD 16.00').decode()}},
            {'filename': 'invoice.pdf', 'body': {'data': first}},
            {'filename': 'invoice.pdf', 'body': {'attachmentId': 'second'}},
        ]}}
        request.side_effect = [listing, message, ProviderError('Temporary failure')]
        with self.assertRaises(ProviderError):
            sync_gmail(connection)
        request.side_effect = [listing, message, {'data': second}]
        sync_gmail(connection)
        self.assertCountEqual(Receipt.objects.values_list('amount', 'currency', 'issued_on'), [
            (Decimal('7.00'), 'EUR', date(2026, 10, 10)),
            (Decimal('9.00'), 'USD', date(2026, 10, 12)),
        ])
        payment = ImportedPayment.objects.get()
        self.assertEqual((payment.amount, payment.paid_on), (Decimal('16.00'), date(2026, 10, 15)))

    @patch('finance.connections.plaid')
    def test_failed_plaid_page_does_not_advance_cursor(self, plaid):
        from .connections import ProviderError
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', cursor='old', encrypted_tokens=encrypt_tokens({'access_token': 'secret'}))
        plaid.side_effect = [{'added': [], 'next_cursor': 'new', 'has_more': True}, ProviderError('Unavailable')]
        with self.assertRaises(ProviderError):
            sync_plaid(connection)
        connection.refresh_from_db()
        self.assertEqual(connection.cursor, 'old')

    def test_archived_imported_payments_survive_backup_without_credentials(self):
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens=encrypt_tokens({'access_token': 'never-export'}))
        ImportedPayment.objects.create(connection=connection, remote_id='one', merchant='Studio', amount=30, currency='USD', paid_on=self.today)
        content = build_archive(self.user)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertNotIn('never-export', archive.read('subly.json').decode())
        result = self.client.post('/api/finance/backup/restore/', {'file': SimpleUploadedFile('backup.zip', content), 'confirm': 'RESTORE'})
        self.assertEqual(result.status_code, 200, result.content)
        archived = Connection.objects.get(enabled=False)
        self.assertEqual(tokens_for(archived), {})
        self.assertEqual(archived.payments.count(), 1)

    def test_revoked_team_access_hides_detailed_budget(self):
        team = create_team(name='Team', user=self.user)
        budget = SpendingBudget.objects.create(user=self.user, team=team, currency='USD', monthly_limit=100)
        TeamMembership.objects.filter(user=self.user, team=team).delete()
        self.assertEqual(self.client.get('/api/finance/budgets/').json()['budgets'], [])
        self.assertIn(self.client.delete(f'/api/finance/budgets/{budget.pk}/').status_code, (403, 404))
        self.assertTrue(SpendingBudget.objects.filter(pk=budget.pk).exists())

    def test_member_credential_permission_is_enforced_in_both_routes(self):
        team = create_team(name='Team', user=self.other)
        TeamMembership.objects.create(user=self.user, team=team, role='member', can_view_credentials=False)
        sub = self.sub(user=self.other, team=team, account_password='secret')
        self.assertEqual(self.client.post(f'/api/accounts/teams/{team.pk}/subscriptions/{sub.pk}/password/').status_code, 403)
        self.assertEqual(self.client.post(f'/accounts/teams/{team.pk}/subscriptions/{sub.pk}/password/').status_code, 403)

    def test_queued_email_honors_disabled_preference_before_delivery(self):
        pref = NotificationPreference.objects.create(user=self.user, email_enabled=False)
        notification = InAppNotification.objects.create(recipient=self.user, title='Renewal', event_type='renewal')
        NotificationDelivery.objects.create(notification=notification, email=True, deliver_after=timezone.now() - timedelta(minutes=1))
        self.assertEqual(deliver_queued(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_scheduled_sync_cannot_run_concurrently(self):
        from .connections import sync_connection, ProviderError
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens='unused', syncing_until=timezone.now() + timedelta(minutes=10))
        with self.assertRaises(ProviderError):
            sync_connection(connection)

    def test_notification_preferences_defer_and_snooze_delivery(self):
        now = datetime(2026, 11, 19, 23, 0, tzinfo=dt_timezone.utc)
        pref = NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='08:00')
        pref.refresh_from_db()
        notification = InAppNotification.objects.create(recipient=self.user, title='Renewal', body='Due soon', event_type='renewal')
        with patch('finance.delivery.timezone.now', return_value=now):
            route_notification(notification, True)
        self.assertEqual(NotificationDelivery.objects.get().deliver_after.hour, 8)
        self.assertEqual(len(mail.outbox), 0)
        result = self.post(f'notifications/{notification.pk}/snooze/', {'hours': 24})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/dashboard/notifications/').json()['notifications'], [])

    def test_disabled_email_and_digest_do_not_send_individual_alerts(self):
        NotificationPreference.objects.create(user=self.user, email_enabled=False)
        notification = InAppNotification.objects.create(recipient=self.user, title='Renewal', body='Due soon', event_type='renewal')
        route_notification(notification, True)
        self.assertEqual(len(mail.outbox), 0)
        pref = NotificationPreference.objects.get(); pref.email_enabled = True; pref.digest = 'daily'; pref.save()
        route_notification(notification, True)
        self.assertEqual(len(mail.outbox), 0)
        # The digest cutoff must be after the alert, including afternoon runs.
        now = timezone.now().replace(hour=12) + timedelta(days=1)
        with patch('finance.delivery.timezone.now', return_value=now):
            self.assertEqual(send_digests(), 1)
            self.assertEqual(send_digests(), 0)

    def test_push_endpoint_cannot_target_private_network(self):
        self.assertEqual(self.post('notifications/push/', {'endpoint': 'https://127.0.0.1/private', 'keys': {'auth': 'abc', 'p256dh': 'abc'}}).status_code, 400)

    def test_snoozed_old_notification_resurfaces_and_enters_digest(self):
        now = timezone.now().replace(hour=12)
        pref = NotificationPreference.objects.create(user=self.user, email_enabled=True, digest='daily', last_digest_at=now - timedelta(days=1))
        notification = InAppNotification.objects.create(recipient=self.user, title='Old renewal', event_type='renewal')
        InAppNotification.objects.filter(pk=notification.pk).update(created_at=now - timedelta(days=7))
        NotificationDelivery.objects.create(notification=notification, email=True, deliver_after=now - timedelta(minutes=1), snoozed_until=now - timedelta(minutes=1))
        with patch('finance.delivery.timezone.now', return_value=now):
            self.assertEqual(deliver_queued(), 1)
            self.assertEqual(send_digests(), 1)
        self.assertIn('Old renewal', mail.outbox[0].body)

    def test_invalid_and_partial_preferences_are_rejected(self):
        result = self.client.put('/api/finance/notifications/preferences/', {'email_enabled': True, 'quiet_start': '22:00'}, content_type='application/json')
        self.assertEqual(result.status_code, 400)

    def test_digest_includes_every_eligible_notification(self):
        now = timezone.now().replace(hour=12)
        NotificationPreference.objects.create(user=self.user, digest='daily', last_digest_at=now - timedelta(days=1))
        with patch('finance.delivery.timezone.now', return_value=now):
            InAppNotification.objects.bulk_create([
                InAppNotification(recipient=self.user, title=f'Renewal {index}', event_type='renewal')
                for index in range(101)
            ])
            self.assertEqual(send_digests(), 1)
            self.assertEqual(send_digests(), 0)
        self.assertEqual(len(mail.outbox), 1)
        for index in range(101):
            self.assertIn(f'Renewal {index}\n', mail.outbox[0].body)

    def test_legacy_logout_removes_only_the_current_browsers_push(self):
        current = PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/current',
            keys={}, session_key=self.client.session.session_key)
        other = PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/other',
            keys={}, session_key='other-browser')
        result = self.client.post('/accounts/logout/')
        self.assertEqual(result.status_code, 302)
        self.assertFalse(PushSubscription.objects.filter(pk=current.pk).exists())
        self.assertTrue(PushSubscription.objects.filter(pk=other.pk).exists())

    @patch('pywebpush.webpush')
    def test_push_rejects_expired_and_revoked_browser_sessions(self, webpush):
        from django.test import Client
        from accounts.models import AccountSecurity
        from .delivery import send_push

        notification = InAppNotification.objects.create(recipient=self.user, title='Private renewal', event_type='renewal')
        for reason in ('expired', 'password', 'mfa'):
            with self.subTest(reason=reason):
                browser = Client()
                browser.force_login(self.user)
                session = browser.session
                row = PushSubscription.objects.create(user=self.user, endpoint=f'https://fcm.googleapis.com/{reason}',
                    keys={}, session_key=session.session_key)
                if reason == 'expired':
                    session.set_expiry(-1)
                    session.save()
                elif reason == 'password':
                    self.user.set_password('Changed-password-example-73')
                    self.user.save(update_fields=['password'])
                else:
                    AccountSecurity.objects.create(user=self.user, enabled=True, revision='new-enrollment')
                self.assertTrue(send_push(notification))
                webpush.assert_not_called()
                self.assertFalse(PushSubscription.objects.filter(pk=row.pk).exists())

    @patch('pywebpush.webpush')
    def test_push_delivers_to_a_current_authenticated_browser(self, webpush):
        from accounts.models import AccountSecurity
        from .delivery import send_push

        row = PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/current',
            keys={}, session_key=self.client.session.session_key)
        notification = InAppNotification.objects.create(recipient=self.user, title='Renewal', event_type='renewal')
        self.assertTrue(send_push(notification))
        webpush.assert_called_once()
        self.assertTrue(PushSubscription.objects.filter(pk=row.pk).exists())
        AccountSecurity.objects.create(user=self.user, enabled=True, revision='verified-enrollment')
        session = self.client.session
        session['mfa_revision'] = 'verified-enrollment'
        session.save()
        webpush.reset_mock()
        self.assertTrue(send_push(notification))
        webpush.assert_called_once()
        self.assertTrue(PushSubscription.objects.filter(pk=row.pk).exists())

    def test_password_change_keeps_push_bound_to_the_current_session(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.user.set_password('Password-example-42')
                self.user.save(update_fields=['password'])
                self.client.force_login(self.user)
                previous_key = self.client.session.session_key
                current = PushSubscription.objects.create(user=self.user,
                    endpoint=f'https://fcm.googleapis.com/current-{legacy}', keys={}, session_key=previous_key)
                payload = {'old_password': 'Password-example-42',
                    'new_password1': 'New-password-example-73', 'new_password2': 'New-password-example-73'}
                if legacy:
                    result = self.client.post('/accounts/settings/', {'form_type': 'password', **payload})
                    self.assertEqual(result.status_code, 302)
                else:
                    result = self.client.post('/api/accounts/settings/password/', payload, content_type='application/json')
                    self.assertEqual(result.status_code, 200, result.content)
                current.refresh_from_db()
                self.assertNotEqual(self.client.session.session_key, previous_key)
                self.assertEqual(current.session_key, self.client.session.session_key)
                self.assertEqual(self.client.post('/api/accounts/logout/').status_code, 204)
                self.assertFalse(PushSubscription.objects.filter(pk=current.pk).exists())
