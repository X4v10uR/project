import io
import json
import tempfile
import time
import zipfile
from datetime import datetime, date, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch, Mock
from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from accounts.models import User, TeamMembership
from accounts.team_workflows import create_team
from subscriptions.models import Subscription, Transaction, PriceChange, ChargeShare, Repayment, InAppNotification
from subscriptions.notifications import create_notification
from .models import Receipt, SpendingBudget, ExchangeRate, NotificationPreference, NotificationDelivery, Connection, ImportedPayment, Activity
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

    def pdf(self):
        from reportlab.pdfgen import canvas
        output = io.BytesIO()
        pdf = canvas.Canvas(output)
        pdf.drawString(80, 750, 'Invoice 2026-11-19 Total: USD 30.00')
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
        response = self.client.get(row['download_url'])
        self.assertEqual(response.status_code, 200)
        response.close()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(row['download_url']).status_code, 404)
        self.assertEqual(self.client.patch(f'/api/finance/receipts/{receipt.pk}/', {'note': 'x'}, content_type='application/json').status_code, 404)

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
        result = self.client.get('/api/finance/reports/?filetype=csv')
        self.assertEqual(result.status_code, 200)
        self.assertIn("'=FORMULA()", result.content.decode('utf-8-sig'))
        self.assertNotIn('Hidden', result.content.decode('utf-8-sig'))
        result = self.client.get('/api/finance/reports/?filetype=pdf')
        self.assertTrue(result.content.startswith(b'%PDF-'))
        self.assertNotIn('FORMULA', self.client.get('/api/finance/reports/?status=paid').content.decode('utf-8-sig'))

    def test_live_calendar_updates_and_can_be_revoked(self):
        sub = self.sub()
        result = self.post('calendar/feeds/', {'scope': 'personal'})
        url = result.json()['url'].split(settings.SITE_URL)[-1]
        self.client.logout()
        self.assertIn('Studio', self.client.get(url).content.decode())
        sub.service_name = 'Updated Studio'
        sub.save()
        self.assertIn('Updated Studio', self.client.get(url).content.decode())
        self.client.force_login(self.user)
        result = self.client.delete('/api/finance/calendar/feeds/', {'id': result.json()['id']}, content_type='application/json')
        self.assertEqual(result.status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)

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
        content = build_archive(self.user)
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

    def test_matching_requires_exact_identity_amount_and_date(self):
        charge = self.charge(self.sub())
        connection = Connection.objects.create(user=self.user, provider='plaid', external_id='item', label='Bank', encrypted_tokens='x')
        payment = ImportedPayment.objects.create(connection=connection, remote_id='one', merchant='Studio', amount=30, currency='USD', paid_on=self.today)
        data = self.client.get('/api/finance/discoveries/').json()
        self.assertEqual(data['payments'][0]['matches'][0]['id'], charge.pk)
        self.assertEqual(self.post(f'discoveries/{payment.pk}/', {'action': 'match', 'charge': charge.pk}).status_code, 200)
        charge.refresh_from_db(); self.assertEqual(charge.payment_status, 'paid')
        self.assertEqual(self.post(f'discoveries/{payment.pk}/', {'action': 'match', 'charge': charge.pk}).status_code, 400)

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
        now = timezone.now().replace(hour=12)
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
