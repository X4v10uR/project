"""Server-side Plaid/Gmail adapters. Imported data always goes through review."""
import base64
import hashlib
import json
import re
import secrets
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import urlencode
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from accounts.security import require_recent
from subscriptions.models import Subscription, Transaction
from subscriptions.models import _account_password_encrypt_fernet, _account_password_decrypt_fernets
from .models import Connection, ImportedPayment, ImportedMessage, Receipt
from .documents import parse_invoice, validate_file, extract_receipt
from .permissions import log_activity


class ProviderError(Exception):
    pass


def encrypt_tokens(tokens):
    return _account_password_encrypt_fernet().encrypt(json.dumps(tokens).encode()).decode()


def tokens_for(connection):
    for cipher in _account_password_decrypt_fernets():
        try:
            return json.loads(cipher.decrypt(connection.encrypted_tokens.encode()))
        except Exception:
            continue
    raise ProviderError('Reconnect this account; its stored credentials cannot be read.')


def provider_request(method, url, **kwargs):
    try:
        response = requests.request(method, url, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        # Do not expose provider responses, access tokens or mail content in logs/errors.
        raise ProviderError('The provider request failed. Try syncing again or reconnect the account.') from exc


def plaid(path, **body):
    if not settings.PLAID_CLIENT_ID or not settings.PLAID_SECRET:
        raise ProviderError('Configure PLAID_CLIENT_ID and PLAID_SECRET on the server first.')
    if settings.PLAID_ENV not in ('sandbox', 'production'):
        raise ProviderError('PLAID_ENV must be sandbox or production.')
    return provider_request('POST', f'https://{settings.PLAID_ENV}.plaid.com/{path}',
        json={'client_id': settings.PLAID_CLIENT_ID, 'secret': settings.PLAID_SECRET, **body})


def connection_data(row):
    return {'id': row.pk, 'provider': row.provider, 'label': row.label, 'last_synced_at': row.last_synced_at, 'error': row.error, 'enabled': row.enabled}


@api_view(['GET'])
def connections(request):
    return Response({'connections': [connection_data(c) for c in Connection.objects.filter(user=request.user)],
        'plaid_configured': bool(settings.PLAID_CLIENT_ID and settings.PLAID_SECRET),
        'gmail_configured': bool(settings.GMAIL_CLIENT_ID and settings.GMAIL_CLIENT_SECRET), 'plaid_environment': settings.PLAID_ENV})


@api_view(['POST'])
def plaid_link(request):
    require_recent(request)
    try:
        data = plaid('link/token/create', client_name='Subly', user={'client_user_id': str(request.user.pk)},
            products=['transactions'], country_codes=settings.PLAID_COUNTRY_CODES, language='en')
    except ProviderError as exc:
        raise ValidationError(str(exc))
    return Response({'link_token': data['link_token']}, headers={'Cache-Control': 'no-store'})


@api_view(['POST'])
def plaid_exchange(request):
    require_recent(request)
    public_token = serializers.CharField(max_length=1000).run_validation(request.data.get('public_token'))
    label = serializers.CharField(max_length=255).run_validation(request.data.get('label', 'Bank account'))
    try:
        data = plaid('item/public_token/exchange', public_token=public_token)
    except ProviderError as exc:
        raise ValidationError(str(exc))
    row, _ = Connection.objects.update_or_create(user=request.user, provider='plaid', external_id=data['item_id'],
        defaults={'label': label, 'encrypted_tokens': encrypt_tokens({'access_token': data['access_token']}), 'cursor': '', 'error': '', 'enabled': True})
    return Response(connection_data(row), status=201)


@api_view(['POST'])
def gmail_start(request):
    require_recent(request)
    if not settings.GMAIL_CLIENT_ID or not settings.GMAIL_CLIENT_SECRET:
        raise ValidationError('Configure the Gmail OAuth client on the server first.')
    state = secrets.token_urlsafe(32)
    request.session['gmail_oauth'] = {'state': state, 'at': timezone.now().timestamp(), 'user': request.user.pk}
    query = urlencode({'client_id': settings.GMAIL_CLIENT_ID, 'redirect_uri': settings.GMAIL_REDIRECT_URI,
        'response_type': 'code', 'scope': 'https://www.googleapis.com/auth/gmail.readonly',
        'access_type': 'offline', 'prompt': 'consent', 'state': state})
    return Response({'url': 'https://accounts.google.com/o/oauth2/v2/auth?' + query}, headers={'Cache-Control': 'no-store'})


@api_view(['GET'])
def gmail_callback(request):
    saved = request.session.pop('gmail_oauth', {})
    if not saved or saved.get('user') != request.user.pk or timezone.now().timestamp() - saved.get('at', 0) > 600 or not secrets.compare_digest(saved.get('state', ''), request.query_params.get('state', '')):
        raise ValidationError('The connection request expired or is invalid. Start again from Connections.')
    if request.query_params.get('error'):
        return HttpResponseRedirect(settings.SITE_URL.rstrip('/') + '/planning/connections/?connection=cancelled')
    code = serializers.CharField(max_length=4000).run_validation(request.query_params.get('code'))
    try:
        tokens = provider_request('POST', 'https://oauth2.googleapis.com/token', data={
            'code': code, 'client_id': settings.GMAIL_CLIENT_ID, 'client_secret': settings.GMAIL_CLIENT_SECRET,
            'redirect_uri': settings.GMAIL_REDIRECT_URI, 'grant_type': 'authorization_code'})
        profile = provider_request('GET', 'https://gmail.googleapis.com/gmail/v1/users/me/profile', headers={'Authorization': 'Bearer ' + tokens['access_token']})
        old = Connection.objects.filter(user=request.user, provider='gmail', external_id=profile['emailAddress']).first()
        if not tokens.get('refresh_token') and old:
            tokens['refresh_token'] = tokens_for(old).get('refresh_token')
        if not tokens.get('refresh_token'):
            raise ProviderError('Gmail did not grant offline access. Reconnect and grant access.')
        tokens['expires_at'] = timezone.now().timestamp() + int(tokens.get('expires_in', 3600))
        Connection.objects.update_or_create(user=request.user, provider='gmail', external_id=profile['emailAddress'],
            defaults={'label': profile['emailAddress'], 'encrypted_tokens': encrypt_tokens(tokens), 'error': '', 'enabled': True})
    except ProviderError as exc:
        raise ValidationError(str(exc))
    return HttpResponseRedirect(settings.SITE_URL.rstrip('/') + '/planning/connections/?connection=connected')


def sync_plaid(connection):
    access_token = tokens_for(connection)['access_token']
    cursor = connection.cursor
    pages = []
    for _ in range(50):
        result = plaid('transactions/sync', access_token=access_token, cursor=cursor, count=500)
        pages.append(result)
        cursor = result['next_cursor']
        if not result['has_more']:
            break
    else:
        raise ProviderError('Too many transactions for one sync. No cursor changes were saved.')
    with transaction.atomic():
        for page in pages:
            for row in page.get('added', []) + page.get('modified', []):
                if not row.get('iso_currency_code') or Decimal(str(row['amount'])) <= 0:
                    continue
                ImportedPayment.objects.update_or_create(connection=connection, remote_id=row['transaction_id'], defaults={
                    'merchant': (row.get('merchant_name') or row['name'])[:100], 'amount': row['amount'],
                    'currency': row['iso_currency_code'], 'paid_on': row['date'], 'description': row['name'][:500],
                    'pending': bool(row.get('pending')), 'removed': False})
            for row in page.get('removed', []):
                ImportedPayment.objects.filter(connection=connection, remote_id=row['transaction_id']).update(removed=True)
        connection.cursor = cursor
        connection.save(update_fields=['cursor'])


def gmail_token(connection):
    tokens = tokens_for(connection)
    if tokens.get('expires_at', 0) < timezone.now().timestamp() + 60:
        fresh = provider_request('POST', 'https://oauth2.googleapis.com/token', data={'grant_type': 'refresh_token',
            'client_id': settings.GMAIL_CLIENT_ID, 'client_secret': settings.GMAIL_CLIENT_SECRET, 'refresh_token': tokens['refresh_token']})
        tokens.update(fresh)
        tokens['expires_at'] = timezone.now().timestamp() + int(fresh.get('expires_in', 3600))
        connection.encrypted_tokens = encrypt_tokens(tokens)
        connection.save(update_fields=['encrypted_tokens'])
    return tokens['access_token']


def mail_text(payload):
    texts = []
    if payload.get('mimeType', '').startswith('text/') and payload.get('body', {}).get('data'):
        raw = payload['body']['data']
        text = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)).decode(errors='replace')[:100000]
        texts.append(re.sub('<[^>]+>', ' ', text))
    for part in payload.get('parts', []):
        texts.extend(mail_text(part))
    return texts


def mail_parts(payload):
    yield payload
    for part in payload.get('parts', []):
        yield from mail_parts(part)


def sync_gmail(connection):
    headers = {'Authorization': 'Bearer ' + gmail_token(connection)}
    root = 'https://gmail.googleapis.com/gmail/v1/users/me/messages'
    page = None
    processed = 0
    for _ in range(20):
        params = {'q': 'newer_than:90d (subject:receipt OR subject:invoice OR subject:subscription OR subject:renewal)', 'maxResults': 100}
        if page:
            params['pageToken'] = page
        result = provider_request('GET', root, headers=headers, params=params)
        for message in result.get('messages', []):
            if ImportedMessage.objects.filter(connection=connection, remote_id=message['id']).exists():
                continue
            mail = provider_request('GET', root + '/' + message['id'], headers=headers, params={'format': 'full'})
            payload = mail.get('payload', {})
            mail_headers = {h['name'].lower(): h['value'] for h in payload.get('headers', [])}
            text = '\n'.join(mail_text(payload))[:100000]
            parsed = parse_invoice(text)
            try:
                day = parsedate_to_datetime(mail_headers.get('date', '')).date()
            except (TypeError, ValueError):
                day = timezone.localdate()
            sender, _ = parseaddr(mail_headers.get('from', ''))
            merchant = (sender or mail_headers.get('subject', 'Email receipt'))[:100]
            for part in mail_parts(payload):
                filename = part.get('filename', '')
                body = part.get('body', {})
                if not filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')) or body.get('size', 0) > 10 * 1024 * 1024:
                    continue
                note = f'Captured from Gmail connection {connection.pk}, message {message["id"]}, file {filename}'[:500]
                existing = Receipt.objects.filter(user=connection.user, note=note).first()
                if existing:
                    if existing.amount is not None and existing.currency and 'amount' not in parsed:
                        parsed.update(amount=existing.amount, currency=existing.currency)
                    continue
                raw = body.get('data')
                if not raw and body.get('attachmentId'):
                    attachment = provider_request('GET', root + '/' + message['id'] + '/attachments/' + body['attachmentId'], headers=headers)
                    raw = attachment.get('data')
                if not raw:
                    continue
                file = ContentFile(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)), name=filename)
                try:
                    kind = validate_file(file)
                except ValidationError:
                    continue
                receipt = Receipt.objects.create(user=connection.user, file=file, filename=filename[:255], content_type=kind,
                    merchant=merchant, amount=parsed.get('amount'), currency=parsed.get('currency', ''), issued_on=parsed.get('issued_on', day), note=note)
                extract_receipt(receipt)
                if receipt.amount is not None and receipt.currency and 'amount' not in parsed:
                    parsed.update(amount=receipt.amount, currency=receipt.currency)
            if 'amount' in parsed and parsed.get('currency'):
                ImportedPayment.objects.update_or_create(connection=connection, remote_id=message['id'], defaults={'merchant': merchant,
                    'amount': parsed['amount'], 'currency': parsed['currency'], 'paid_on': parsed.get('issued_on', day),
                    'description': mail_headers.get('subject', '')[:500]})
            ImportedMessage.objects.get_or_create(connection=connection, remote_id=message['id'])
            processed += 1
            if processed >= 50:
                # Subsequent runs skip captured messages and continue the initial scan.
                return
        page = result.get('nextPageToken')
        if not page:
            return
    raise ProviderError('The first 2,000 matching messages were scanned. Narrow your mailbox or sync again after archiving older mail.')


def sync_connection(connection):
    if not connection.enabled:
        raise ProviderError('This is an archived connection. Connect the provider again to sync new data.')
    claimed = Connection.objects.filter(pk=connection.pk).filter(Q(syncing_until__isnull=True) | Q(syncing_until__lt=timezone.now())).update(syncing_until=timezone.now() + timedelta(minutes=30))
    if not claimed:
        raise ProviderError('This account is already syncing. Wait for its current sync to finish.')
    try:
        if connection.provider == 'plaid':
            sync_plaid(connection)
        else:
            sync_gmail(connection)
        connection.last_synced_at = timezone.now()
        connection.error = ''
        connection.save(update_fields=['last_synced_at', 'error'])
    except (ProviderError, ValueError, KeyError, TypeError) as exc:
        connection.error = str(exc) if isinstance(exc, ProviderError) else 'The provider returned an unsupported response. Reconnect and retry.'
        connection.save(update_fields=['error'])
        raise ProviderError(connection.error) from exc
    finally:
        Connection.objects.filter(pk=connection.pk).update(syncing_until=None)


@api_view(['POST', 'DELETE'])
def connection_detail(request, pk):
    connection = get_object_or_404(Connection, pk=pk, user=request.user)
    if request.method == 'DELETE':
        require_recent(request)
        if not connection.enabled:
            connection.delete()
            return Response(status=204)
        tokens = tokens_for(connection)
        try:
            if connection.provider == 'plaid':
                plaid('item/remove', access_token=tokens['access_token'])
            else:
                # Revoke at Google before deleting the local credentials.
                response = requests.post('https://oauth2.googleapis.com/revoke', data={'token': tokens.get('refresh_token', tokens['access_token'])}, timeout=20)
                response.raise_for_status()
        except (ProviderError, requests.RequestException):
            raise ValidationError('Provider revocation failed. Retry, or revoke access with the provider before removing it.')
        connection.delete()
        return Response(status=204)
    try:
        sync_connection(connection)
    except ProviderError as exc:
        raise ValidationError(str(exc))
    return Response(connection_data(connection))


def normalize(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def payment_matches(payment):
    if payment.pending or payment.removed or payment.charge_id:
        return []
    rows = Transaction.objects.filter(user=payment.connection.user, team__isnull=True, currency=payment.currency,
        payment_status__in=['scheduled', 'failed'], charged_for_date__range=[payment.paid_on - timedelta(days=3), payment.paid_on + timedelta(days=3)])
    return [r for r in rows if r.amount == payment.amount and normalize(r.service_name_snapshot) == normalize(payment.merchant)]


@api_view(['GET'])
def discoveries(request):
    rows = list(ImportedPayment.objects.filter(connection__user=request.user, dismissed=False, removed=False).select_related('connection').order_by('-paid_on')[:1000])
    groups = defaultdict(list)
    for row in rows:
        if not row.pending:
            groups[(normalize(row.merchant), row.currency)].append(row)
    candidates = []
    for (_, currency), values in groups.items():
        dates = sorted({r.paid_on for r in values})
        if len(dates) < 2:
            continue
        days = (dates[-1] - dates[-2]).days
        cycle = 'weekly' if 5 <= days <= 9 else 'fourweekly' if 26 <= days <= 28 else 'monthly' if 29 <= days <= 33 else 'quarterly' if 85 <= days <= 95 else 'yearly' if 360 <= days <= 370 else None
        if cycle and not Subscription.objects.filter(user=request.user, team__isnull=True, service_name__iexact=values[0].merchant, currency=currency).exists():
            candidates.append({'service': values[0].merchant, 'cost': str(values[0].amount), 'currency': currency,
                'billing_cycle': cycle, 'start_date': dates[-1], 'occurrences': len(dates), 'payment_ids': [v.pk for v in values]})
    return Response({'candidates': candidates, 'payments': [{'id': r.pk, 'merchant': r.merchant, 'amount': str(r.amount), 'currency': r.currency,
        'date': r.paid_on, 'provider': r.connection.provider, 'pending': r.pending, 'charge': r.charge_id, 'description': r.description,
        'matches': [{'id': m.pk, 'service': m.service_name_snapshot, 'date': m.charged_for_date} for m in payment_matches(r)]} for r in rows]})


@api_view(['POST'])
@transaction.atomic
def discovery_action(request, pk):
    row = get_object_or_404(ImportedPayment.objects.select_for_update().select_related('connection'), pk=pk, connection__user=request.user)
    action = serializers.ChoiceField(choices=['dismiss', 'match']).run_validation(request.data.get('action'))
    if action == 'dismiss':
        row.dismissed = True
        row.save(update_fields=['dismissed'])
    else:
        charge_id = serializers.IntegerField(min_value=1).run_validation(request.data.get('charge'))
        get_object_or_404(Transaction.objects.select_for_update(), pk=charge_id, user=request.user, team__isnull=True)
        matches = payment_matches(row)
        match = next((m for m in matches if m.pk == charge_id), None)
        if match is None:
            raise ValidationError('The match is no longer available. Amount, currency, merchant and date must agree.')
        if ImportedPayment.objects.filter(charge=match).exclude(pk=row.pk).exists():
            raise ValidationError('This charge is already matched to another imported payment.')
        match.payment_status = 'paid'
        match.save(update_fields=['payment_status'])
        row.charge = match
        row.subscription = match.subscription
        row.save(update_fields=['charge', 'subscription'])
        if match.subscription:
            log_activity(request.user, match.subscription, 'payment.matched', {'provider': row.connection.provider, 'charge': match.pk})
    return Response({'saved': True})
