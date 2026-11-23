import base64
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from .connections import ProviderError, encrypt_tokens, mail_text, sync_gmail, tokens_for
from .documents import parse_invoice
from .models import Connection, ImportedMessage, ImportedPayment, Receipt


def text_part(text, kind='text/plain', encoding='utf-8', **extra):
    return {'mimeType': kind, 'body': {'data': base64.urlsafe_b64encode(text.encode(encoding)).decode()}, **extra}


class MailTextTests(SimpleTestCase):
    def test_plain_text_preserves_literal_angle_brackets(self):
        self.assertEqual(mail_text(text_part('Usage < 10; Total: USD 30.00')), ['Usage < 10; Total: USD 30.00'])

    def test_html_decodes_entities_and_ignores_styles_and_scripts(self):
        payload = text_part('<head><style>.price { content: "USD 99.00"; }</style></head>'
            '<script>let price = "USD 88.00";</script>'
            '<p>Total:&nbsp;<span>&#85;SD</span><b>30.00</b></p>', kind='text/html')
        text = ' '.join(mail_text(payload))
        self.assertEqual(parse_invoice(text)['amount'], Decimal('30.00'))
        self.assertNotIn('99.00', text)
        self.assertNotIn('88.00', text)

    def test_declared_charset_and_unknown_charset_fallback(self):
        payload = text_part('Café Total: EUR 30.00', encoding='iso-8859-1',
            headers=[{'name': 'Content-Type', 'value': 'text/plain; charset=iso-8859-1'}])
        self.assertIn('Café', mail_text(payload)[0])
        payload['headers'][0]['value'] = 'text/plain; charset=not-a-real-charset'
        self.assertEqual(parse_invoice(mail_text(payload)[0])['amount'], Decimal('30.00'))

    def test_non_text_charset_cannot_crash_import(self):
        payload = text_part('Total: USD 30.00',
            headers=[{'name': 'Content-Type', 'value': 'text/plain; charset=idna'}])
        self.assertEqual(parse_invoice(mail_text(payload)[0])['amount'], Decimal('30.00'))

    def test_oversize_external_text_body_is_not_downloaded(self):
        payload = {'mimeType': 'text/plain', 'body': {'attachmentId': 'huge', 'size': 11 * 1024 * 1024}}
        with patch('finance.connections.provider_request') as request:
            self.assertEqual(mail_text(payload, load_body=request), [])
        request.assert_not_called()

    def test_alternatives_prefer_plain_text_and_skip_text_attachments(self):
        payload = {'mimeType': 'multipart/mixed', 'parts': [
            text_part('Unrelated Total: USD 99.00', filename='other.txt'),
            {'mimeType': 'multipart/alternative', 'parts': [
                text_part('<p>Total USD 88.00</p>', kind='text/html'),
                text_part('Total USD 30.00'),
            ]},
        ]}
        text = ' '.join(mail_text(payload))
        self.assertEqual(parse_invoice(text)['amount'], Decimal('30.00'))
        self.assertNotIn('99.00', text)

    def test_alternative_html_can_supply_details_missing_from_plain_text(self):
        payload = {'mimeType': 'multipart/alternative', 'parts': [
            text_part('View your receipt online.'),
            text_part('<p>Total:&nbsp;USD 30.00</p>', kind='text/html'),
        ]}
        self.assertEqual(parse_invoice(' '.join(mail_text(payload)))['amount'], Decimal('30.00'))

    def test_inline_html_does_not_split_currency_or_amount(self):
        payload = text_part('<p>Total: <span>U</span><b>SD</b><span>3</span><span>0.00</span></p>', kind='text/html')
        self.assertEqual(parse_invoice(' '.join(mail_text(payload)))['amount'], Decimal('30.00'))

    def test_malformed_plain_part_falls_back_to_html(self):
        payload = {'mimeType': 'multipart/alternative', 'parts': [
            {'mimeType': 'text/plain', 'body': {'data': 'malformed!'}},
            text_part('<p>Total USD 30.00</p>', kind='text/html'),
        ]}
        self.assertEqual(parse_invoice(' '.join(mail_text(payload)))['amount'], Decimal('30.00'))


class GmailImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('mail-import@example.test')
        self.connection = Connection.objects.create(user=self.user, provider='gmail', external_id=self.user.email,
            label='Mail', encrypted_tokens=encrypt_tokens({'access_token': 'test-token',
                'expires_at': timezone.now().timestamp() + 3600}))

    @patch('finance.connections.provider_request')
    def test_missing_date_uses_gmail_received_time(self, request):
        received = datetime(2026, 1, 20, 2, tzinfo=UTC)
        request.side_effect = [
            {'messages': [{'id': 'invoice'}]},
            {'internalDate': str(int(received.timestamp()) * 1000), 'payload': text_part('Total: USD 10.00')},
        ]
        sync_gmail(self.connection)
        self.assertEqual(ImportedPayment.objects.get().paid_on, date(2026, 1, 20))

    @patch('finance.connections.provider_request')
    def test_large_mailbox_resumes_after_the_scan_limit(self, request):
        ImportedMessage.objects.bulk_create([
            ImportedMessage(connection=self.connection, remote_id=str(i)) for i in range(20)
        ])
        request.side_effect = [
            {'messages': [{'id': str(i)}], 'nextPageToken': str(i + 1)} for i in range(20)
        ]
        sync_gmail(self.connection)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.cursor, '20')
        request.side_effect = [{'messages': [{'id': 'older'}]}, {'payload': text_part('Total: USD 10.00')}]
        sync_gmail(self.connection)
        self.assertEqual(request.call_args_list[-2].kwargs['params']['pageToken'], '20')
        self.assertTrue(ImportedMessage.objects.filter(remote_id='older').exists())
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.cursor, '')

    @patch('finance.connections.provider_request')
    def test_batch_limit_resumes_in_the_middle_of_a_page(self, request):
        listing = {'messages': [{'id': str(i)} for i in range(51)], 'nextPageToken': 'next'}
        message = {'payload': text_part('Total: USD 10.00')}
        request.side_effect = [listing] + [message] * 50
        sync_gmail(self.connection)
        self.assertEqual(ImportedMessage.objects.count(), 50)
        request.side_effect = [listing, message, {'messages': []}]
        sync_gmail(self.connection)
        self.assertEqual(ImportedMessage.objects.count(), 51)
        self.assertEqual(ImportedPayment.objects.count(), 51)

    @patch('finance.connections.provider_request')
    def test_expired_page_token_restarts_and_deleted_message_does_not_block_sync(self, request):
        self.connection.cursor = 'expired'
        self.connection.save(update_fields=['cursor'])
        request.side_effect = [
            ProviderError('Invalid page token', status_code=400),
            {'messages': [{'id': 'deleted'}, {'id': 'kept'}]},
            ProviderError('Message no longer exists', status_code=404),
            {'payload': text_part('Total: USD 12.00')},
        ]
        sync_gmail(self.connection)
        self.assertNotIn('pageToken', request.call_args_list[1].kwargs['params'])
        self.assertEqual(ImportedPayment.objects.get().remote_id, 'kept')

    @patch('finance.connections.provider_request')
    def test_sender_names_are_decoded_and_bare_senders_remain_identifiable(self, request):
        encoded = '=?utf-8?b?' + base64.b64encode('Café, Studio'.encode()).decode() + '?='
        request.side_effect = [
            {'messages': [{'id': 'encoded'}, {'id': 'bare'}]},
            {'payload': text_part('Total: EUR 30.00', headers=[
                {'name': 'From', 'value': encoded + ' <studio@example.test>'},
                {'name': 'Subject', 'value': 'Invoice'},
            ])},
            {'payload': text_part('Total: USD 12.00', headers=[
                {'name': 'From', 'value': 'billing@example.test'},
                {'name': 'Subject', 'value': 'Invoice'},
            ])},
        ]
        sync_gmail(self.connection)
        self.assertEqual(ImportedPayment.objects.get(remote_id='encoded').merchant, 'Café, Studio')
        self.assertEqual(ImportedPayment.objects.get(remote_id='bare').merchant, 'billing@example.test')

    @patch('finance.connections.provider_request')
    def test_malformed_attachment_does_not_block_this_or_later_messages(self, request):
        request.side_effect = [
            {'messages': [{'id': 'bad-attachment'}, {'id': 'later'}]},
            {'payload': {'mimeType': 'multipart/mixed', 'parts': [
                text_part('Total: USD 30.00'),
                {'filename': 'invoice.pdf', 'mimeType': 'application/pdf', 'body': {'data': 'invalid!'}},
            ]}},
            {'payload': text_part('Total: EUR 12.00')},
        ]
        sync_gmail(self.connection)
        self.assertEqual(ImportedPayment.objects.count(), 2)
        self.assertEqual(ImportedMessage.objects.count(), 2)
        self.assertFalse(Receipt.objects.exists())
        request.side_effect = [{'messages': [{'id': 'bad-attachment'}, {'id': 'later'}]}]
        sync_gmail(self.connection)
        self.assertEqual(ImportedPayment.objects.count(), 2)

    @patch('finance.connections.provider_request')
    def test_receipt_text_stored_as_attachment_is_imported(self, request):
        content = text_part('Total: USD 30.00')['body']['data']
        request.side_effect = [
            {'messages': [{'id': 'external-body'}]},
            {'payload': {'mimeType': 'text/plain',
                'body': {'attachmentId': 'body-part', 'size': 16}}},
            {'data': content},
        ]
        sync_gmail(self.connection)
        payment = ImportedPayment.objects.get(remote_id='external-body')
        self.assertEqual(payment.amount, Decimal('30.00'))
        self.assertTrue(request.call_args.args[1].endswith('/external-body/attachments/body-part'))
        self.assertFalse(Receipt.objects.exists())

    @patch('finance.connections.provider_request')
    def test_failed_external_body_download_remains_eligible_for_retry(self, request):
        listing = {'messages': [{'id': 'retry-body'}]}
        message = {'payload': {'mimeType': 'multipart/alternative', 'parts': [
            {'mimeType': 'text/plain', 'body': {'attachmentId': 'body-part', 'size': 16}},
        ]}}
        request.side_effect = [listing, message, ProviderError('Temporary failure')]
        with self.assertRaises(ProviderError):
            sync_gmail(self.connection)
        self.assertFalse(ImportedMessage.objects.exists())
        request.side_effect = [listing, message, text_part('Total: USD 30.00')['body']]
        sync_gmail(self.connection)
        self.assertEqual(ImportedPayment.objects.get(remote_id='retry-body').amount, Decimal('30.00'))

    def test_unicode_oauth_state_is_rejected_without_server_error(self):
        self.client.force_login(self.user)
        session = self.client.session
        session['gmail_oauth'] = {'state': 'expected-state', 'at': timezone.now().timestamp(), 'user': self.user.pk}
        session.save()
        self.client.raise_request_exception = False
        response = self.client.get('/api/finance/connections/gmail/callback/', {'state': 'é', 'code': 'test'})
        self.assertEqual(response.status_code, 400)

    @patch('finance.connections.provider_request')
    def test_valid_oauth_state_connects_once_and_stores_offline_credentials(self, request):
        self.client.force_login(self.user)
        session = self.client.session
        session['gmail_oauth'] = {'state': 'expected-state', 'at': timezone.now().timestamp(), 'user': self.user.pk}
        session.save()
        request.side_effect = [
            {'access_token': 'new-access', 'refresh_token': 'offline-refresh', 'expires_in': 3600},
            {'emailAddress': 'receipts@example.test'},
        ]
        url = '/api/finance/connections/gmail/callback/'
        response = self.client.get(url, {'state': 'expected-state', 'code': 'test'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/planning/connections/?connection=connected', response.url)
        connection = Connection.objects.get(external_id='receipts@example.test')
        self.assertEqual(tokens_for(connection)['refresh_token'], 'offline-refresh')
        self.assertNotIn('offline-refresh', connection.encrypted_tokens)
        self.assertEqual(self.client.get(url, {'state': 'expected-state', 'code': 'test'}).status_code, 400)
        self.assertEqual(request.call_count, 2)
