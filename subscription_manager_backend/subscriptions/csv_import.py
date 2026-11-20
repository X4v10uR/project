import csv
import json
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.core.exceptions import ValidationError as FormError
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.models import User
from .api_serializers import SubscriptionInput, subscription_form
from .models import Subscription
from .views import CSV_FORMULA_PREFIXES
from .workflows import prepare_participants, save_subscription


MAX_ROWS = 500
REQUIRED = {'service_name', 'total_cost', 'billing_cycle', 'start_date'}
FORM_FIELDS = ('service_name', 'plan_name', 'category', 'billing_cycle', 'currency', 'status',
               'start_date', 'paid_through', 'trial_end_date', 'cancel_by_date', 'renewal_time', 'display_color', 'notes', 'account_email', 'split_type',
               'cancellation_url', 'cancellation_state', 'cancellation_notes', 'access_until', 'pause_from', 'resume_on', 'introductory_cost', 'introductory_until')


def read_rows(upload):
    if upload is None or upload.size > 1024 * 1024:
        raise serializers.ValidationError({'file': 'Choose a UTF-8 CSV file up to 1 MB.'})
    try:
        reader = csv.reader(StringIO(upload.read().decode('utf-8-sig'), newline=''), strict=True)
        headers = [name.strip().lower().replace(' ', '_') for name in next(reader, [])]
        headers = ['total_cost' if key == 'cost' else key for key in headers]
        missing = sorted(REQUIRED.difference(headers))
        if missing:
            raise serializers.ValidationError({'file': 'Missing columns: ' + ', '.join(missing)})
        if len(set(headers)) != len(headers):
            raise serializers.ValidationError({'file': 'Use a unique name for each column.'})
        rows = []
        for number, values in enumerate(reader, 2):
            if not any(value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise serializers.ValidationError({'file': f'Row {number} has the wrong number of columns.'})
            if len(rows) >= MAX_ROWS:
                raise serializers.ValidationError({'file': f'Choose a file with at most {MAX_ROWS} subscriptions.'})
            row = dict(zip(headers, values))
            if {'your_cost', 'renewal_date', 'participants', 'is_shared'} <= row.keys():
                # Undo the spreadsheet text escape in Subly exports before matching names.
                for key in ('service_name', 'plan_name', 'category', 'account_email', 'notes', 'participants'):
                    value = row.get(key, '')
                    if value.startswith("'") and (value[1:].lstrip().startswith(CSV_FORMULA_PREFIXES)
                                                  or ('participant_shares' in row and value.startswith("''"))):
                        row[key] = value[1:]
            rows.append((number, row))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise serializers.ValidationError({'file': 'Use UTF-8 and enclose values containing commas in double quotes.'}) from exc
    if not rows:
        raise serializers.ValidationError({'file': 'Add at least one subscription row.'})
    return rows


def csv_boolean(raw, default):
    if not raw.strip():
        return default
    value = serializers.BooleanField()
    return value.run_validation(raw.strip().lower())


def prepare_row(row, user):
    fields = {name: row[name] for name in FORM_FIELDS if row.get(name, '').strip()}
    fields.setdefault('category', 'Other')
    fields['cost'] = row['total_cost']
    fields['is_shared'] = csv_boolean(row.get('is_shared', ''), False)
    fields['reminders_enabled'] = csv_boolean(row.get('reminders_enabled', ''), True)
    names = row.get('participants', '')
    try:
        participants = (json.loads(row['participant_shares']) if row.get('participant_shares')
                        else [{'name': name.strip()} for name in names.split(',') if name.strip()])
        offsets = [day.strip() for day in row.get('reminder_offsets', '').split(',') if day.strip()]
    except ValueError as exc:
        raise serializers.ValidationError('Participant shares must be a JSON array of names and shares.') from exc
    nested = SubscriptionInput(data={'participants': participants, 'reminder_offsets': offsets})
    nested.is_valid(raise_exception=True)
    data = nested.validated_data
    sub = subscription_form(fields, user=user).save(commit=False)
    sub.user = user
    if data['participants'] and not sub.is_shared:
        raise serializers.ValidationError('Set Is Shared to Yes for subscriptions with participants.')
    prepare_participants(sub, data['participants'])
    if sub.is_shared and row.get('your_cost'):
        try:
            matches = sub.user_cost == Decimal(row['your_cost'])
        except InvalidOperation:
            matches = False
        if not matches:
            raise serializers.ValidationError('Your Cost does not match the split. Supply Split Type and Participant Shares.')
    return sub, data


def identity(service, plan, email):
    return tuple((part or '').strip().casefold() for part in (service, plan, email))


def validate_rows(rows, user):
    existing = Subscription.objects.filter(user=user, team__isnull=True).values_list('service_name', 'plan_name', 'account_email')
    seen = {identity(*item) for item in existing}
    preview, pending = [], []
    for number, row in rows:
        item = {'row': number, 'service': row['service_name'], 'status': 'invalid'}
        try:
            sub, data = prepare_row(row, user)
            key = identity(sub.service_name, sub.plan_name, sub.account_email)
            item.update(cost=str(sub.cost), currency=sub.currency, cycle=sub.billing_cycle, start=sub.start_date.isoformat())
            if key in seen:
                item['status'] = 'duplicate'
            else:
                item['status'] = 'ready'
                seen.add(key)
                pending.append((sub, data))
        except serializers.ValidationError as exc:
            item['errors'] = exc.detail
        except FormError as exc:
            item['errors'] = exc.messages
        preview.append(item)
    return preview, pending


@api_view(['POST'])
@parser_classes([MultiPartParser])
def import_subscriptions(request):
    mode = request.data.get('mode', 'preview')
    if mode not in ('preview', 'confirm'):
        raise serializers.ValidationError({'mode': 'Choose preview or confirm.'})
    rows = read_rows(request.FILES.get('file'))
    if mode == 'preview':
        preview, _ = validate_rows(rows, request.user)
        return Response({'rows': preview, 'imported': 0})

    with transaction.atomic():
        # Concurrent imports for the same account must see the first commit's duplicates.
        User.objects.select_for_update().get(pk=request.user.pk)
        preview, pending = validate_rows(rows, request.user)
        if any(row['status'] == 'invalid' for row in preview):
            return Response({'rows': preview, 'imported': 0, 'detail': 'Correct the invalid rows before importing.'}, status=400)
        for sub, data in pending:
            save_subscription(sub, actor=request.user, participants=data['participants'], reminder_offsets=data['reminder_offsets'])
    return Response({'rows': preview, 'imported': len(pending)})
