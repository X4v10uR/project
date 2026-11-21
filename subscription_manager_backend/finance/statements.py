"""Preview bank statement rows before adding outgoing payments to a private ledger."""
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Connection, ImportedPayment


DEBIT_COLUMNS = ('debit', 'debits', 'debit amount', 'withdrawal', 'withdrawals', 'withdrawal amount')
CREDIT_COLUMNS = ('credit', 'credits', 'credit amount', 'deposit', 'deposits', 'deposit amount')
AMOUNT_PATTERN = re.compile(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?')
HEADERS = {
    'date': ('date', 'transaction date', 'posting date', 'posted date', 'booking date'),
    'merchant': ('merchant', 'payee', 'description', 'transaction description', 'name'),
    'amount': ('amount', 'transaction amount', *DEBIT_COLUMNS),
    'currency': ('currency', 'currency code', 'iso currency code'),
    'reference': ('transaction id', 'reference', 'id', 'transaction reference'),
}
DATE_FORMATS = {'iso': '%Y-%m-%d', 'mdy': '%m/%d/%Y', 'dmy': '%d/%m/%Y'}


def digest(parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def read_statement(file):
    if not file or file.size > 1024 * 1024:
        raise serializers.ValidationError('Choose a UTF-8 CSV up to 1 MB.')
    try:
        content = file.read().decode('utf-8-sig')
        try:
            dialect = csv.Sniffer().sniff(content[:8192], delimiters=',;\t')
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(content, newline=''), dialect=dialect, strict=True)
        headers = [s.strip() for s in next(reader, [])]
        if not headers or len(headers) > 100 or not all(headers) or len(set(headers)) != len(headers):
            raise serializers.ValidationError('Use a header row with a unique name for each column.')
        rows = []
        for line, cells in enumerate(reader, 2):
            if not any(s.strip() for s in cells):
                continue
            if len(cells) != len(headers):
                raise serializers.ValidationError(f'Row {line} has a different number of columns from the header.')
            if len(rows) == 500:
                raise serializers.ValidationError('Import up to 500 rows at a time.')
            rows.append((line, dict(zip(headers, (s.strip() for s in cells)))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise serializers.ValidationError('The file must be a valid UTF-8 CSV.') from error
    if not rows:
        raise serializers.ValidationError('The statement contains no payment rows.')
    return headers, rows


def column_mapping(headers, data):
    lookup = {h.lower().replace('_', ' '): h for h in headers}
    mapping = {}
    for field, names in HEADERS.items():
        default = next((lookup[name] for name in names if name in lookup), '')
        name = data.get(f'column_{field}', default)
        if name and name not in headers:
            raise serializers.ValidationError(f'Unknown column for {field}.')
        mapping[field] = name
    used = [name for name in mapping.values() if name]
    if len(set(used)) != len(used):
        raise serializers.ValidationError('Choose a different column for each field.')
    return mapping


def parse_row(row, mapping, date_format, debits, currency):
    try:
        day = datetime.strptime(row[mapping['date']], date_format).date()
    except ValueError as error:
        raise ValueError('Date does not match the selected format.') from error
    # The matching window and projected schedules need dates on either side.
    if day.year < 2 or day.year > 9998:
        raise ValueError('Date is outside the supported range.')
    amount_column = mapping['amount']
    raw = row[amount_column]
    if not raw and amount_column.lower().replace('_', ' ') in DEBIT_COLUMNS:
        for header, value in row.items():
            if header.lower().replace('_', ' ') in CREDIT_COLUMNS and AMOUNT_PATTERN.fullmatch(value):
                if Decimal(value.replace(',', '')) > 0:
                    return None
    if not AMOUNT_PATTERN.fullmatch(raw):
        raise ValueError('Use a numeric amount with up to two decimal places.')
    try:
        amount = Decimal(raw.replace(',', '')).quantize(Decimal('0.01'))
    except InvalidOperation as error:
        raise ValueError('Amount is too large.') from error
    if debits == 'negative':
        amount = -amount
    if amount <= 0:
        return None
    if amount > Decimal('9999999999.99'):
        raise ValueError('Amount is too large.')
    merchant = row[mapping['merchant']]
    if not merchant or len(merchant) > 100:
        raise ValueError('Merchant must contain 1–100 characters.')
    code = row.get(mapping['currency'], '').upper() or currency
    if not re.fullmatch('[A-Z]{3}', code):
        raise ValueError('Use a three-letter currency code.')
    reference = row.get(mapping['reference'], '')
    identity = ['reference', reference] if reference else ['payment', day.isoformat(), merchant.casefold(), str(amount), code]
    return dict(remote_id=digest(identity), merchant=merchant, amount=amount, paid_on=day, currency=code)


@api_view(['POST'])
def import_statement(request):
    headers, raw_rows = read_statement(request.FILES.get('file'))
    data = request.data
    label = serializers.CharField(max_length=100).run_validation(data.get('account', 'Bank statement'))
    mode = serializers.ChoiceField(choices=['preview', 'confirm']).run_validation(data.get('mode', 'preview'))
    date_format = serializers.ChoiceField(choices=list(DATE_FORMATS)).run_validation(data.get('date_format', 'iso'))
    debits = serializers.ChoiceField(choices=['positive', 'negative']).run_validation(data.get('debits', 'positive'))
    currency = serializers.RegexField(r'^[A-Z]{3}$').run_validation(str(data.get('currency', request.user.preferred_currency or 'USD')).upper())
    mapping = column_mapping(headers, data)
    result = {'headers': headers, 'mapping': mapping, 'rows': [], 'ready': 0, 'duplicates': 0, 'skipped': 0, 'errors': 0}
    if any(not mapping[k] for k in ('merchant', 'date', 'amount')):
        if mode == 'confirm':
            raise serializers.ValidationError('Choose date, merchant and amount columns before importing.')
        return Response(result)

    parsed = []
    for line, row in raw_rows:
        item = {'line': line}
        result['rows'].append(item)
        try:
            values = parse_row(row, mapping, DATE_FORMATS[date_format], debits, currency)
            if values:
                item.update(merchant=values['merchant'], amount=values['amount'], date=values['paid_on'], currency=values['currency'])
                parsed.append((item, values))
            else:
                item.update(status='skipped', message='Incoming or zero amount')
                result['skipped'] += 1
        except ValueError as error:
            item.update(status='error', message=str(error))
            result['errors'] += 1
    confirm = mode == 'confirm'
    with transaction.atomic() if confirm else nullcontext():
        if confirm:
            # Serialize confirmations even when this is the user's first statement for the account.
            get_user_model().objects.select_for_update().only('pk').get(pk=request.user.pk)
        review_payments(request.user, label, parsed, result, confirm)
    return Response(result)


def review_payments(user, label, parsed, result, confirm):
    # Portable restore creates separate ledger copies with fresh connection IDs.
    ledgers = Connection.objects.filter(user=user, provider='statement').values_list('pk', 'label')
    ledger_ids = [pk for pk, name in ledgers if name.casefold() == label.casefold()]
    stored = ImportedPayment.objects.filter(
        connection_id__in=ledger_ids, remote_id__in=[v['remote_id'] for _, v in parsed]
    ).values_list('remote_id', 'merchant', 'paid_on', 'amount', 'currency')
    known = defaultdict(set)
    for reference, merchant, day, amount, currency in stored:
        known[reference].add((merchant.casefold(), day, amount, currency))
    new = []
    for item, values in parsed:
        reference = values['remote_id']
        details = (values['merchant'].casefold(), values['paid_on'], values['amount'], values['currency'])
        if known[reference] and known[reference] != {details}:
            item.update(status='error', message='This transaction ID has conflicting payment details.')
            result['errors'] += 1
        elif details in known[reference]:
            item['status'] = 'duplicate'
            result['duplicates'] += 1
        else:
            item['status'] = 'ready'
            result['ready'] += 1
            new.append(values)
        known[reference].add(details)
    if confirm:
        if result['errors']:
            raise serializers.ValidationError('Fix the invalid rows before importing.')
        if new:
            connection, _ = Connection.objects.get_or_create(
                user=user, provider='statement', external_id=digest([label.casefold()]),
                defaults={'label': label, 'enabled': False})
            ImportedPayment.objects.bulk_create([ImportedPayment(connection=connection, **values) for values in new])
            Connection.objects.filter(pk=connection.pk).update(last_synced_at=timezone.now())
        result['imported'] = len(new)
