import hashlib
import secrets
from datetime import timedelta
from decimal import Decimal
import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from accounts.models import Team, TeamMembership
from subscriptions.models import Subscription
from subscriptions.money import monthly_equivalent
from subscriptions.planning import calendar_export
from .models import Receipt, SpendingBudget, ExchangeRate, CalendarFeed, Activity
from .permissions import subscriptions_for, charges_for, subscription_for, require_team, team_permission, log_activity
from .budgets import spend, check_budget
from .documents import validate_file, extract_receipt, csv_response, history_pdf


class ReceiptInput(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = ('merchant', 'amount', 'currency', 'issued_on', 'note')
        extra_kwargs = {'amount': {'min_value': Decimal('0')}}

    def validate_currency(self, value):
        if value and (len(value) != 3 or not value.isascii() or not value.isalpha()):
            raise serializers.ValidationError('Use a three-letter currency code.')
        return value.upper()


def receipts_for(user):
    return Receipt.objects.filter(Q(user=user, team__isnull=True) | Q(team__memberships__user=user)).distinct()


def receipt_data(row, user=None):
    return {'id': row.pk, 'filename': row.filename, **ReceiptInput(row).data,
        'subscription': row.subscription_id, 'charge': row.charge_id, 'team': row.team_id,
        'extraction_status': row.extraction_status, 'created_at': row.created_at,
        'download_url': f'/api/finance/receipts/{row.pk}/file/', 'can_edit': bool(user and team_permission(user, row.team_id, 'pay'))}


@api_view(['GET', 'POST'])
def receipts(request):
    if request.method == 'GET':
        rows = receipts_for(request.user).order_by('-created_at')
        can_upload = True
        if request.query_params.get('subscription'):
            sub = subscription_for(request.user, serializers.IntegerField(min_value=1).run_validation(request.query_params['subscription']))
            rows = rows.filter(subscription=sub)
            can_upload = team_permission(request.user, sub.team_id, 'pay')
        if request.query_params.get('charge'):
            charge = get_object_or_404(charges_for(request.user), pk=serializers.IntegerField(min_value=1).run_validation(request.query_params['charge']))
            rows = rows.filter(charge=charge)
            can_upload = team_permission(request.user, charge.team_id, 'pay')
        return Response({'receipts': [receipt_data(row, request.user) for row in rows[:500]], 'can_upload': can_upload,
            'subscriptions': [{'id': s.pk, 'service': s.service_name, 'team': s.team_id} for s in subscriptions_for(request.user) if team_permission(request.user, s.team_id, 'pay')],
            'ocr_available': bool(settings.TESSERACT_CMD)})
    data = ReceiptInput(data=request.data)
    data.is_valid(raise_exception=True)
    sub = subscription_for(request.user, serializers.IntegerField(min_value=1).run_validation(request.data['subscription']), 'pay') if request.data.get('subscription') else None
    charge = get_object_or_404(charges_for(request.user), pk=serializers.IntegerField(min_value=1).run_validation(request.data['charge'])) if request.data.get('charge') else None
    if charge:
        require_team(request.user, charge.team_id, 'pay')
        if sub and charge.subscription_id != sub.pk:
            raise serializers.ValidationError('The charge belongs to another subscription.')
        sub = charge.subscription or sub
    file = request.FILES.get('file')
    if not file:
        raise serializers.ValidationError('Choose a receipt file.')
    content_type = validate_file(file)
    row = Receipt.objects.create(user=request.user, subscription=sub, charge=charge,
        team_id=charge.team_id if charge else (sub.team_id if sub else None), file=file,
        filename=file.name[:255], content_type=content_type, **data.validated_data)
    extract_receipt(row)
    if sub:
        log_activity(request.user, sub, 'receipt.uploaded', {'filename': row.filename})
    return Response(receipt_data(row, request.user), status=201)


@api_view(['GET', 'PATCH', 'DELETE'])
def receipt_detail(request, pk, download=False):
    row = get_object_or_404(receipts_for(request.user), pk=pk)
    if request.method == 'GET':
        if download:
            response = FileResponse(row.file.open('rb'), as_attachment=True, filename=row.filename, content_type=row.content_type)
            response['Cache-Control'] = 'no-store'
            response['X-Content-Type-Options'] = 'nosniff'
            return response
        return Response({**receipt_data(row, request.user), 'extracted_text': row.extracted_text})
    require_team(request.user, row.team_id, 'pay')
    if request.method == 'DELETE':
        if row.subscription_id:
            log_activity(request.user, row.subscription, 'receipt.deleted', {'filename': row.filename})
        row.file.delete(save=False)
        row.delete()
        return Response(status=204)
    data = ReceiptInput(row, data=request.data, partial=True)
    data.is_valid(raise_exception=True)
    data.save()
    if row.subscription_id:
        log_activity(request.user, row.subscription, 'receipt.updated')
    return Response(receipt_data(row, request.user))


class BudgetInput(serializers.ModelSerializer):
    team_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    class Meta:
        model = SpendingBudget
        fields = ('team_id', 'category', 'currency', 'monthly_limit', 'warning_percent')
        extra_kwargs = {'monthly_limit': {'min_value': Decimal('.01')}, 'warning_percent': {'min_value': 1, 'max_value': 99}}

    def validate_currency(self, value):
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise serializers.ValidationError('Use a three-letter currency code.')
        return value.upper()

    def validate(self, values):
        require_team(self.context['user'], values.get('team_id'), 'pay')
        return values


def budget_data(budget):
    value = spend(budget)
    return {'id': budget.pk, **BudgetInput(budget).data, 'team': budget.team.name if budget.team_id else None,
        'spend': str(value), 'percent': str((value / budget.monthly_limit * 100).quantize(Decimal('.1')))}


@api_view(['GET', 'POST'])
def budgets(request):
    if request.method == 'GET':
        rows = SpendingBudget.objects.filter(user=request.user).filter(Q(team__isnull=True) | Q(team__memberships__user=request.user, team__memberships__role__in=['owner', 'accountant'])).distinct().select_related('team')
        return Response({'budgets': [budget_data(b) for b in rows],
            'teams': list(Team.objects.filter(memberships__user=request.user, memberships__role__in=['owner', 'accountant']).values('id', 'name')),
            'categories': sorted(set(subscriptions_for(request.user).values_list('category', flat=True)))})
    data = BudgetInput(data=request.data, context={'user': request.user})
    data.is_valid(raise_exception=True)
    values = data.validated_data
    with transaction.atomic():
        budget, _ = SpendingBudget.objects.update_or_create(user=request.user, team_id=values.get('team_id'),
            category=values.get('category', ''), currency=values['currency'], defaults=values)
        check_budget(budget.pk)
    return Response(budget_data(budget), status=201)


@api_view(['DELETE'])
def budget_detail(request, pk):
    get_object_or_404(SpendingBudget, pk=pk, user=request.user).delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
def conversion(request):
    base = serializers.RegexField(r'^[A-Za-z]{3}$').run_validation(request.query_params.get('base', request.user.preferred_currency)).upper()
    scope = serializers.ChoiceField(choices=['personal', 'teams']).run_validation(request.query_params.get('scope', 'personal'))
    subs = subscriptions_for(request.user)
    subs = subs.filter(team__isnull=False) if scope == 'teams' else subs.filter(team__isnull=True)
    codes = sorted(set(subs.values_list('currency', flat=True)) - {base})
    error = ''
    if request.method == 'POST' and codes:
        try:
            response = requests.get('https://api.frankfurter.dev/v2/rates', params={'base': base, 'quotes': ','.join(codes)}, timeout=12)
            response.raise_for_status()
            values = response.json()
            with transaction.atomic():
                for row in values:
                    rate = Decimal(str(row['rate']))
                    if row['base'].upper() == base and row['quote'].upper() in codes and rate.is_finite() and rate > 0:
                        ExchangeRate.objects.update_or_create(base=base, quote=row['quote'].upper(),
                            defaults={'rate': rate, 'as_of': row['date'], 'source': 'Frankfurter'})
        except (requests.RequestException, ValueError, KeyError, TypeError, ArithmeticError):
            error = 'Exchange rates could not be refreshed. Previously saved rates are shown where available.'
    rates = {r.quote: r for r in ExchangeRate.objects.filter(base=base, quote__in=codes)}
    total = Decimal('0')
    missing = set()
    today = timezone.localdate()
    for sub in subs.prefetch_related('participants', 'price_changes'):
        if not sub.bills_on(today):
            continue
        value = monthly_equivalent(sub.share_on(today), sub.billing_cycle)
        if sub.currency == base:
            total += value
        elif sub.currency in rates:
            total += value / rates[sub.currency].rate
        else:
            missing.add(sub.currency)
    return Response({'base': base, 'monthly_total': str(total.quantize(Decimal('.01'))), 'complete': not missing,
        'missing': sorted(missing), 'error': error, 'rates': [{'quote': r.quote, 'rate': str(r.rate), 'as_of': r.as_of, 'source': r.source,
            'stale': (today - r.as_of).days > 7} for r in rates.values()]})


@api_view(['GET'])
def report(request):
    from dashboard.api_views import ChargeFilters
    query = ChargeFilters(data=request.query_params)
    query.is_valid(raise_exception=True)
    filters = query.validated_data
    rows = charges_for(request.user).select_related('team')
    rows = rows.filter(team__isnull=False) if filters['scope'] == 'teams' else rows.filter(team__isnull=True)
    if filters.get('service'):
        rows = rows.filter(service_name_snapshot__icontains=filters['service'])
    if filters.get('start'):
        rows = rows.filter(charged_for_date__gte=filters['start'])
    if filters.get('end'):
        rows = rows.filter(charged_for_date__lte=filters['end'])
    status = request.query_params.get('status')
    if status:
        status = serializers.ChoiceField(choices=['scheduled', 'paid', 'failed', 'refunded']).run_validation(status)
        rows = rows.filter(payment_status=status)
    rows = rows.order_by('charged_for_date', 'pk')
    if rows.count() > 10000:
        raise serializers.ValidationError('Narrow the date range to export at most 10,000 charges.')
    format = serializers.ChoiceField(choices=['csv', 'pdf']).run_validation(request.query_params.get('filetype', 'csv'))
    if format == 'pdf':
        return history_pdf(rows, 'Subly charge history')
    return csv_response(['Date', 'Service', 'Team', 'Currency', 'Your amount', 'Payment status'],
        ([r.charged_for_date, r.service_name_snapshot, r.team.name if r.team_id else 'Personal', r.currency, str(r.amount), r.payment_status] for r in rows), 'subly-charge-history.csv')


@api_view(['GET', 'POST', 'DELETE'])
def feeds(request):
    if request.method == 'GET':
        return Response({'feeds': list(CalendarFeed.objects.filter(user=request.user).values('id', 'scope', 'created_at'))})
    if request.method == 'DELETE':
        pk = serializers.IntegerField(min_value=1).run_validation(request.data.get('id'))
        get_object_or_404(CalendarFeed, pk=pk, user=request.user).delete()
        return Response(status=204)
    scope = serializers.ChoiceField(choices=['personal', 'teams']).run_validation(request.data.get('scope', 'personal'))
    token = secrets.token_urlsafe(32)
    feed = CalendarFeed.objects.create(user=request.user, scope=scope, token_hash=hashlib.sha256(token.encode()).hexdigest())
    url = settings.SITE_URL.rstrip('/') + '/api/finance/calendar/' + token + '.ics'
    return Response({'id': feed.pk, 'url': url, 'webcal_url': url.replace('https://', 'webcal://').replace('http://', 'webcal://')}, status=201, headers={'Cache-Control': 'no-store'})


@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def feed_calendar(request, token):
    from dateutil.relativedelta import relativedelta
    feed = get_object_or_404(CalendarFeed.objects.select_related('user'), token_hash=hashlib.sha256(token.encode()).hexdigest())
    # Build a fresh calendar on every fetch, respecting current membership.
    from subscriptions.planning import calendar_events, visible_subscriptions, fold_ical, ical_text
    today = timezone.localdate()
    events = calendar_events(visible_subscriptions(feed.user, feed.scope).prefetch_related('participants', 'price_changes'), today - timedelta(days=30), today + relativedelta(years=1))
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Subly//Live renewals//EN', 'X-WR-CALNAME:Subly renewals', 'REFRESH-INTERVAL;VALUE=DURATION:PT6H', 'X-PUBLISHED-TTL:PT6H']
    for event in events:
        lines += ['BEGIN:VEVENT', f"UID:{feed.user_id}-{event['id']}@subly", f'DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}',
            'DTSTART;VALUE=DATE:' + event['date'].replace('-', ''), 'SUMMARY:' + ical_text(f"{event['service']}: {event['kind']}"), 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return HttpResponse('\r\n'.join(fold_ical(line) for line in lines) + '\r\n', content_type='text/calendar', headers={'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer'})


@api_view(['GET'])
def activity(request):
    rows = Activity.objects.filter(Q(owner=request.user, team__isnull=True) | Q(team__memberships__user=request.user)).distinct().select_related('user')
    if request.query_params.get('subscription'):
        rows = rows.filter(subscription_id=serializers.IntegerField(min_value=1).run_validation(request.query_params['subscription']))
    if request.query_params.get('team'):
        rows = rows.filter(team_id=serializers.IntegerField(min_value=1).run_validation(request.query_params['team']))
    return Response({'activity': [{'id': r.pk, 'actor': r.user.email if r.user_id else 'Deleted account', 'service': r.service,
        'action': r.action, 'changes': r.changes, 'created_at': r.created_at} for r in rows.order_by('-created_at', '-pk')[:200]]})
