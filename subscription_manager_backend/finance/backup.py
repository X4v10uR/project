"""Portable, additive archives. Account secrets and live access grants are excluded."""
import io
import json
import zipfile
import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.files.base import ContentFile
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from accounts.models import Team, TeamMembership
from accounts.security import require_recent
from dashboard.models import BalanceAdjustment
from subly.renderers import ZipRenderer
from subscriptions.models import Card, Subscription, SubscriptionParticipant, ReminderOffset, PriceChange, Transaction, ChargeShare, Repayment, InAppNotification
from .models import Receipt, SpendingBudget, Activity, NotificationPreference, Connection, ImportedPayment
from .budgets import BudgetInput
from .documents import validate_file
from subscriptions.models import TeamRenewal


SUB_FIELDS = ['service_name', 'display_color', 'plan_name', 'category', 'billing_cycle', 'cost', 'user_cost', 'is_shared', 'split_type', 'currency',
    'start_date', 'paid_through', 'trial_end_date', 'cancel_by_date', 'cancellation_url', 'cancellation_state', 'cancellation_notes', 'access_until',
    'pause_from', 'resume_on', 'introductory_cost', 'introductory_until', 'last_reviewed_on', 'usage_rating', 'renewal_date', 'renewal_time',
    'status', 'notes', 'reminders_enabled', 'account_email']
SPECS = {
    'cards': (Card, ['nickname', 'last4', 'brand', 'theme', 'is_primary']),
    'subscriptions': (Subscription, SUB_FIELDS),
    'participants': (SubscriptionParticipant, ['name', 'share_amount']),
    'renewals': (TeamRenewal, ['decision', 'decision_for', 'decided_at']),
    'offsets': (ReminderOffset, ['days_before']),
    'prices': (PriceChange, ['previous_cost', 'cost', 'effective_on']),
    'charges': (Transaction, ['service_name_snapshot', 'amount', 'currency', 'charged_for_date', 'source', 'payment_status', 'shares_captured']),
    'shares': (ChargeShare, ['name', 'amount', 'reimbursed', 'repaid_amount']),
    'repayments': (Repayment, ['amount', 'note']),
    'budgets': (SpendingBudget, ['category', 'currency', 'monthly_limit', 'warning_percent']),
    'balances': (BalanceAdjustment, ['scope', 'currency', 'monthly_limit', 'amount']),
    'receipts': (Receipt, ['filename', 'content_type', 'merchant', 'amount', 'currency', 'issued_on', 'note', 'extracted_text', 'extraction_status']),
    'activity': (Activity, ['service', 'action', 'changes']),
    'notifications': (InAppNotification, ['event_type', 'title', 'body', 'is_read', 'metadata', 'last_reminded_at']),
    'connections': (Connection, ['provider', 'label', 'last_synced_at']),
    'imports': (ImportedPayment, ['remote_id', 'merchant', 'amount', 'currency', 'paid_on', 'description', 'pending', 'removed', 'dismissed']),
}


def records(query, fields, refs=()):
    rows = []
    for obj in query:
        row = {'id': obj.pk, **{name: getattr(obj, name) for name in fields}, **{name: getattr(obj, name) for name in refs}}
        for name in ('created_at', 'charged_at'):
            if hasattr(obj, name):
                row[name] = getattr(obj, name)
        rows.append(row)
    return rows


def build_archive(user):
    team_ids = list(TeamMembership.objects.filter(user=user, role='owner').values_list('team_id', flat=True))
    from django.db.models import Q
    subs = Subscription.objects.filter(Q(user=user, team__isnull=True) | Q(team_id__in=team_ids))
    charges = Transaction.objects.filter(Q(user=user, team__isnull=True) | Q(team_id__in=team_ids))
    charge_ids = list(charges.values_list('pk', flat=True))
    sub_ids = list(subs.values_list('pk', flat=True))
    shares = ChargeShare.objects.filter(charge_id__in=charge_ids)
    queries = {
        'cards': (Card.objects.filter(user=user), ()),
        'subscriptions': (subs, ('team_id', 'card_id')),
        'participants': (SubscriptionParticipant.objects.filter(subscription_id__in=sub_ids), ('subscription_id',)),
        'renewals': (TeamRenewal.objects.filter(subscription_id__in=sub_ids).annotate(
            assigned_to_exporter=Q(assignee__user=user), decided_by_exporter=Q(decided_by=user)
        ), ('subscription_id', 'assigned_to_exporter', 'decided_by_exporter')),
        'offsets': (ReminderOffset.objects.filter(subscription_id__in=sub_ids), ('subscription_id',)),
        'prices': (PriceChange.objects.filter(subscription_id__in=sub_ids), ('subscription_id',)),
        'charges': (charges, ('subscription_id', 'team_id')),
        'shares': (shares, ('charge_id',)),
        'repayments': (Repayment.objects.filter(share__in=shares), ('share_id',)),
        'budgets': (SpendingBudget.objects.filter(user=user).filter(Q(team__isnull=True) | Q(team_id__in=team_ids)), ('team_id',)),
        'balances': (BalanceAdjustment.objects.filter(user=user), ()),
        'receipts': (Receipt.objects.filter(Q(user=user, team__isnull=True) | Q(team_id__in=team_ids)), ('subscription_id', 'charge_id', 'team_id')),
        'activity': (Activity.objects.filter(Q(owner=user, team__isnull=True) | Q(team_id__in=team_ids)), ('subscription_id', 'team_id')),
        'notifications': (InAppNotification.objects.filter(recipient=user), ()),
        'connections': (Connection.objects.filter(user=user), ()),
        'imports': (ImportedPayment.objects.filter(connection__user=user), ('connection_id', 'subscription_id', 'charge_id')),
    }
    data = {'version': 1, 'exported_at': timezone.now(), 'account_email': user.email,
        'teams': [{'id': t.pk, 'name': t.name, 'members': list(t.memberships.values('user__email', 'role', 'can_view_credentials'))} for t in Team.objects.filter(pk__in=team_ids)],
        'preferences': {'timezone': user.timezone, 'preferred_currency': user.preferred_currency},
        'exclusions': ['login/MFA secrets', 'stored provider passwords', 'integration access tokens', 'calendar access tokens', 'team invitations']}
    for key, (query, refs) in queries.items():
        data[key] = records(query, SPECS[key][1], refs)
    # A personal statement can link to a team charge the user manages as an accountant.
    # The portable backup includes team records only when the user owns that team.
    exported_subscriptions, exported_charges = set(sub_ids), set(charge_ids)
    for row in data['imports']:
        if row['subscription_id'] not in exported_subscriptions:
            row['subscription_id'] = None
        if row['charge_id'] not in exported_charges:
            row['charge_id'] = None
    pref = NotificationPreference.objects.filter(user=user).first()
    data['notification_preferences'] = {f: getattr(pref, f) for f in ('email_enabled', 'push_enabled', 'digest', 'quiet_start', 'quiet_end')} if pref else None
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('subly.json', json.dumps(data, cls=DjangoJSONEncoder))
        total = 0
        for row in queries['receipts'][0]:
            if not row.file:
                raise serializers.ValidationError(f'Receipt {row.pk} is missing from storage. Repair it before exporting.')
            try:
                with row.file.open('rb') as file:
                    content = file.read(10 * 1024 * 1024 + 1)
            except FileNotFoundError:
                raise serializers.ValidationError(f'Receipt {row.pk} is missing from storage. Repair it before exporting.')
            total += len(content)
            if len(content) > 10 * 1024 * 1024 or total > 100 * 1024 * 1024:
                raise serializers.ValidationError('This archive exceeds 100 MB. Export receipt groups separately.')
            archive.writestr(f'receipts/{row.pk}', content)
    return output.getvalue()


def read_archive(file):
    if not file or file.size > 110 * 1024 * 1024:
        raise serializers.ValidationError('Choose a Subly ZIP archive up to 110 MB.')
    try:
        archive = zipfile.ZipFile(file)
        entries = archive.infolist()
        if len(entries) > 10001 or sum(e.file_size for e in entries) > 120 * 1024 * 1024 or any(e.file_size > 20 * 1024 * 1024 for e in entries):
            raise ValueError()
        if len({e.filename for e in entries}) != len(entries):
            raise ValueError()
        data = json.loads(archive.read('subly.json'))
        if not isinstance(data, dict) or data.get('version') != 1 or any(not isinstance(data.get(k, []), list) for k in [*SPECS, 'teams']):
            raise ValueError()
        if not isinstance(data.get('preferences', {}), dict):
            raise ValueError()
        if sum(len(data.get(k, [])) for k in [*SPECS, 'teams']) > 50000:
            raise ValueError()
        for key in [*SPECS, 'teams']:
            ids = [r['id'] for r in data.get(key, [])]
            if any(not isinstance(pk, int) or pk < 1 for pk in ids) or len(ids) != len(set(ids)):
                raise ValueError()
        return archive, data
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise serializers.ValidationError('The archive is invalid, unsupported, or too large.') from exc


def create_record(key, row, **refs):
    model, fields = SPECS[key]
    obj = model(**{f: model._meta.get_field(f).to_python(row[f]) for f in fields if f in row}, **refs)
    # Stored passwords are never materialized from an archive.
    if key == 'cards' and obj.is_primary and Card.objects.filter(user=obj.user, is_primary=True).exists():
        obj.is_primary = False
    if key == 'charges' and obj.subscription_id is None:
        # Deleting a subscription retains its charges and their snapshots.
        obj.full_clean(exclude=['subscription'])
    elif key == 'receipts':
        obj.full_clean(exclude=['file'])
    else:
        obj.full_clean()
    if key in ('cards', 'subscriptions', 'charges', 'shares', 'repayments') and hasattr(obj, 'amount') and obj.amount < 0:
        raise serializers.ValidationError('Amounts cannot be negative.')
    if key in ('subscriptions', 'prices'):
        for field in ('cost', 'user_cost', 'introductory_cost', 'previous_cost'):
            value = getattr(obj, field, None)
            if value is not None and value < 0:
                raise serializers.ValidationError('Prices cannot be negative.')
    if key == 'shares' and (obj.repaid_amount < 0 or obj.repaid_amount > obj.amount):
        raise serializers.ValidationError('A repaid share cannot exceed its amount.')
    dates = {f: model._meta.get_field(f).to_python(row[f]) for f in ('created_at', 'charged_at') if f in row and hasattr(obj, f)}
    if any(value is None for value in dates.values()):
        raise serializers.ValidationError('An archived timestamp is missing.')
    if key == 'subscriptions' and obj.renewal_date:
        dates['renewal_date'] = obj.renewal_date
    try:
        obj.save()
        if dates:
            model.objects.filter(pk=obj.pk).update(**dates)
    except Exception:
        if key == 'receipts' and obj.file and obj.file._committed:
            obj.file.delete(save=False)
        raise
    return obj


def restore_archive(user, archive, data):
    files = []
    maps = {k: {} for k in [*SPECS, 'teams']}
    def ref(kind, row, key, required=False):
        old = row.get(key)
        if old is None and not required:
            return None
        if old not in maps[kind]:
            raise serializers.ValidationError(f'Invalid {kind} reference in archive.')
        return maps[kind][old]
    try:
        with transaction.atomic():
            for row in data.get('teams', []):
                name = serializers.CharField(max_length=120).run_validation(row.get('name'))
                team = Team.objects.create(name=name, created_by=user)
                TeamMembership.objects.create(team=team, user=user, role='owner')
                maps['teams'][row['id']] = team
            for key in ('cards', 'subscriptions', 'renewals', 'participants', 'offsets', 'prices', 'charges', 'shares', 'repayments', 'receipts', 'activity', 'notifications', 'connections', 'imports'):
                for row in data.get(key, []):
                    refs = {}
                    if key in ('cards', 'subscriptions', 'charges', 'receipts', 'connections'):
                        refs['user'] = user
                    if key in ('subscriptions', 'charges', 'receipts', 'activity'):
                        refs['team'] = ref('teams', row, 'team_id')
                    if key == 'subscriptions':
                        # A team subscription may have used another payer's card, which is not exported.
                        refs['card'] = maps['cards'].get(row.get('card_id'))
                    if key in ('participants', 'offsets', 'prices', 'charges', 'receipts', 'activity', 'imports'):
                        refs['subscription'] = ref('subscriptions', row, 'subscription_id', key in ('participants', 'offsets', 'prices'))
                    if key == 'renewals':
                        sub = ref('subscriptions', row, 'subscription_id', required=True)
                        if sub.team_id is None:
                            raise serializers.ValidationError('A renewal decision requires a team subscription.')
                        refs['subscription'] = sub
                        if data.get('account_email') == user.email:
                            if row.get('assigned_to_exporter') is True:
                                refs['assignee'] = TeamMembership.objects.get(team_id=sub.team_id, user=user)
                            if row.get('decided_by_exporter') is True:
                                refs['decided_by'] = user
                    if key in ('shares', 'receipts', 'imports'):
                        refs['charge'] = ref('charges', row, 'charge_id', key == 'shares')
                    if key == 'repayments':
                        refs.update(share=ref('shares', row, 'share_id', True), recorded_by=user)
                    if key == 'activity':
                        refs.update(owner=user, user=user)
                    if key == 'connections':
                        from .connections import encrypt_tokens
                        refs.update(external_id='restored-' + uuid.uuid4().hex, enabled=False, encrypted_tokens=encrypt_tokens({}))
                    if key == 'imports':
                        refs['connection'] = ref('connections', row, 'connection_id', True)
                    if key == 'notifications':
                        refs.update(recipient=user, link_url='/dashboard/notifications/')
                    if key == 'receipts':
                        raw = archive.read(f'receipts/{row["id"]}')
                        file = ContentFile(raw, name=row.get('filename', 'receipt.pdf'))
                        refs['content_type'] = validate_file(file)
                        row = {k: v for k, v in row.items() if k != 'content_type'}
                        refs['file'] = file
                    obj = create_record(key, row, **refs)
                    maps[key][row['id']] = obj
                    if key == 'receipts':
                        files.append(obj.file.name)
            for row in data.get('budgets', []):
                team = ref('teams', row, 'team_id')
                budget = BudgetInput(data={**row, 'team_id': team.pk if team else None}, context={'user': user})
                budget.is_valid(raise_exception=True)
                maps['budgets'][row['id']] = budget.save()
            for row in data.get('balances', []):
                values = {f: BalanceAdjustment._meta.get_field(f).to_python(row[f]) for f in SPECS['balances'][1] if f in row}
                if values['scope'] not in ('personal', 'teams'):
                    raise serializers.ValidationError('Invalid balance scope.')
                balance, _ = BalanceAdjustment.objects.update_or_create(user=user, scope=values.pop('scope'), currency=values.pop('currency'), defaults=values)
                maps['balances'][row['id']] = balance
            pref = data.get('notification_preferences')
            if pref:
                from .delivery import PreferenceInput
                parsed = PreferenceInput(data=pref)
                parsed.is_valid(raise_exception=True)
                NotificationPreference.objects.update_or_create(user=user, defaults={**parsed.validated_data, 'push_enabled': False})
            for share in maps['shares'].values():
                total = sum((r.amount for r in share.repayments.all()), Decimal('0'))
                if total and total != share.repaid_amount:
                    raise serializers.ValidationError('Repayment totals do not agree with the recorded share.')
            preferences = data.get('preferences', {})
            from zoneinfo import available_timezones
            currency = serializers.RegexField(r'^[A-Za-z]{3}$').run_validation(preferences.get('preferred_currency', user.preferred_currency)).upper()
            zone = preferences.get('timezone', user.timezone)
            if zone not in available_timezones():
                raise serializers.ValidationError('The archive contains an invalid timezone.')
            user.preferred_currency, user.timezone = currency, zone
            user.save(update_fields=['preferred_currency', 'timezone'])
            for sub in maps['subscriptions'].values():
                log = {'source': 'Subly archive', 'original_export': data.get('exported_at')}
                Activity.objects.create(owner=user, user=user, subscription=sub, team=sub.team, service=sub.service_name, action='archive.restored', changes=log)
    except Exception as exc:
        from .models import private_storage
        storage = private_storage()
        for name in files:
            storage.delete(name)
        if isinstance(exc, serializers.ValidationError):
            raise
        if isinstance(exc, (ModelValidationError, ValueError, KeyError, TypeError, ArithmeticError, zipfile.BadZipFile)):
            raise serializers.ValidationError('Archive validation failed. No database changes were saved.') from exc
        raise
    return {key: len(value) for key, value in maps.items()}


@api_view(['POST'])
@renderer_classes([JSONRenderer, ZipRenderer])
def backup_export(request):
    require_recent(request)
    content = build_archive(request.user)
    return HttpResponse(content, content_type='application/zip', headers={'Content-Disposition': 'attachment; filename="subly-backup.zip"', 'Cache-Control': 'no-store'})


@api_view(['POST'])
def backup_restore(request):
    require_recent(request)
    archive, data = read_archive(request.FILES.get('file'))
    try:
        if request.data.get('confirm') != 'RESTORE':
            return Response({'preview': {key: len(data.get(key, [])) for key in [*SPECS, 'teams']},
                'exported_at': data.get('exported_at'), 'account_email': data.get('account_email'),
                'notice': 'Restore adds new copies. Your existing subscriptions remain. You become payer/owner of restored teams; re-invite other members and reconnect integrations. Account secrets are excluded.'})
        result = restore_archive(request.user, archive, data)
        from accounts.api_views import account_user
        return Response({'restored': result, 'user': account_user(request.user)})
    finally:
        archive.close()
