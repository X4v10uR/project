"""Decision tools built from the same schedule and recorded payments as billing."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from accounts.models import TeamMembership
from subly.renderers import CalendarRenderer
from .api_views import _subscription_for
from .models import ChargeShare, PriceChange, Repayment, Subscription, Transaction
from .money import monthly_equivalent
from .services import renewals_between
from .workflows import change_subscription_status


def visible_subscriptions(user, scope):
    if scope == 'personal':
        return Subscription.objects.filter(user=user, team__isnull=True)
    return Subscription.objects.filter(team__memberships__user=user).distinct()


class Selection(serializers.Serializer):
    scope = serializers.ChoiceField(choices=['personal', 'teams'], default='personal')
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, data):
        start = data.setdefault('start', timezone.localdate())
        if 'end' not in data:
            data['end'] = date.max if start.year == date.max.year else start + relativedelta(years=1) - timedelta(days=1)
        if not 0 <= (data['end'] - data['start']).days <= 731:
            raise serializers.ValidationError('Select a range of up to two years.')
        return data


def selection(request):
    query = Selection(data=request.query_params)
    query.is_valid(raise_exception=True)
    return query.validated_data


def amount(value):
    return format(value, '.2f')


def calendar_events(subscriptions, start, end):
    events = []
    for sub in subscriptions:
        if sub.status == 'cancelled' or sub.cancellation_state == 'confirmed':
            continue
        for day in renewals_between(sub, start, end):
            events.append({'id': f'{sub.pk}-payment-{day}', 'subscription_id': sub.pk,
                'team_id': sub.team_id,
                'service': sub.service_name, 'kind': 'payment', 'date': day.isoformat(),
                'amount': amount(sub.share_on(day)), 'currency': sub.currency})
        for field, kind in [('trial_end_date', 'trial'), ('cancel_by_date', 'deadline'), ('resume_on', 'resume'), ('pause_from', 'pause')]:
            day = getattr(sub, field)
            if day and start <= day <= end:
                events.append({'id': f'{sub.pk}-{kind}-{day}', 'subscription_id': sub.pk,
                    'team_id': sub.team_id,
                    'service': sub.service_name, 'kind': kind, 'date': day.isoformat(),
                    'amount': None, 'currency': sub.currency})
    return sorted(events, key=lambda row: (row['date'], row['service'], row['kind']))


@api_view(['GET'])
def calendar(request):
    query = selection(request)
    subs = visible_subscriptions(request.user, query['scope']).prefetch_related('price_changes', 'participants')
    return Response({'events': calendar_events(subs, query['start'], query['end'])})


def ical_text(value):
    return str(value).replace('\\', '\\\\').replace('\r', '').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def fold_ical(line):
    # RFC 5545 folds at 75 octets without cutting a UTF-8 sequence.
    lines, current = [], ''
    for char in line:
        if len((current + char).encode('utf-8')) > 75:
            lines.append(current)
            current = ' '
        current += char
    return '\r\n'.join([*lines, current])


@api_view(['GET', 'HEAD'])
@renderer_classes([JSONRenderer, CalendarRenderer])
def calendar_export(request):
    query = selection(request)
    events = calendar_events(visible_subscriptions(request.user, query['scope']).prefetch_related('price_changes', 'participants'), query['start'], query['end'])
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//DUES//Renewals//EN', 'CALSCALE:GREGORIAN']
    labels = {'payment': 'Payment', 'trial': 'Trial ends', 'deadline': 'Cancel by', 'pause': 'Pause begins', 'resume': 'Resume'}
    for event in events:
        summary = f"{event['service']}: {labels[event['kind']]}"
        if event['amount'] is not None:
            summary += f" ({event['currency']} {event['amount']})"
        lines += ['BEGIN:VEVENT', f"UID:{request.user.pk}-{event['id']}@subly", f"DTSTAMP:{timezone.now():%Y%m%dT%H%M%SZ}",
            'DTSTART;VALUE=DATE:' + event['date'].replace('-', ''), 'SUMMARY:' + ical_text(summary),
            'DESCRIPTION:Tracked in DUES. Confirm cancellation with your provider.', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return HttpResponse('\r\n'.join(fold_ical(line) for line in lines) + '\r\n', content_type='text/calendar; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="dues-renewals.ics"', 'Cache-Control': 'no-store'})


@api_view(['GET'])
def insights(request):
    query = selection(request)
    today = timezone.localdate()
    month = today.replace(day=1)
    previous = month - relativedelta(months=1)
    next_month = month + relativedelta(months=1)
    year_end = today + relativedelta(years=1) - timedelta(days=1)
    subs = list(visible_subscriptions(request.user, query['scope']).prefetch_related('price_changes', 'participants'))
    if query['scope'] == 'personal':
        charges = Transaction.objects.filter(user=request.user, team__isnull=True)
    else:
        charges = Transaction.objects.filter(team__memberships__user=request.user).distinct()
    categories, totals, service_current, service_previous = defaultdict(Decimal), defaultdict(lambda: defaultdict(Decimal)), defaultdict(Decimal), defaultdict(Decimal)
    for sub in subs:
        if sub.bills_on(today):
            rate = monthly_equivalent(sub.share_on(today), sub.billing_cycle)
            categories[(sub.currency, sub.category)] += rate
            totals[sub.currency]['monthly_commitment'] += rate
        for day in renewals_between(sub, today, year_end):
            totals[sub.currency]['annual_projection'] += sub.share_on(day)
        for day in renewals_between(sub, max(today, month), next_month - timedelta(days=1)):
            # Today's charge may already be recorded; include it exactly once.
            if not charges.filter(subscription=sub, charged_for_date=day).exists():
                value = sub.share_on(day)
                totals[sub.currency]['month_scheduled'] += value
                service_current[(sub.currency, sub.service_name)] += value
    for charge in charges.filter(charged_for_date__gte=previous, charged_for_date__lt=next_month):
        current = charge.charged_for_date >= month
        key = 'month_scheduled' if current else 'previous_scheduled'
        if charge.payment_status != 'refunded':
            totals[charge.currency][key] += charge.amount
            (service_current if current else service_previous)[(charge.currency, charge.service_name_snapshot)] += charge.amount
        if charge.payment_status == 'paid':
            totals[charge.currency]['month_paid' if current else 'previous_paid'] += charge.amount
    keys = ['monthly_commitment', 'annual_projection', 'month_scheduled', 'previous_scheduled', 'month_paid', 'previous_paid']
    result = []
    for currency, values in sorted(totals.items()):
        delta = values['month_scheduled'] - values['previous_scheduled']
        reasons = [{'service': name, 'change': amount(service_current[(code, name)] - service_previous[(code, name)])}
            for code, name in set(service_current) | set(service_previous) if code == currency and service_current[(code, name)] != service_previous[(code, name)]]
        result.append({'currency': currency, **{key: amount(values[key]) for key in keys}, 'change': amount(delta),
            'reasons': sorted(reasons, key=lambda row: -abs(Decimal(row['change'])))[:8]})
    return Response({'totals': result, 'categories': [{'currency': code, 'category': category, 'monthly': amount(value)} for (code, category), value in sorted(categories.items())],
        'month': month.isoformat(), 'previous_month': previous.isoformat(),
        'explanation': 'Current month includes recorded charges and remaining scheduled payments. Previous month uses recorded history only; missing history can affect comparisons. Paid totals require manual confirmation.'})


@api_view(['GET'])
def review_inbox(request):
    query = selection(request)
    today = timezone.localdate()
    subs = list(visible_subscriptions(request.user, query['scope']).exclude(status='cancelled').prefetch_related('price_changes', 'participants'))
    duplicates = defaultdict(list)
    items = []
    owned = set(request.user.team_memberships.filter(role='owner').values_list('team_id', flat=True))
    for sub in subs:
        if sub.bills_on(today):
            duplicates[(sub.team_id, sub.service_name.strip().casefold(), (sub.account_email or '').strip().casefold())].append(sub.pk)
    for sub in subs:
        reasons = []
        if sub.trial_end_date and 0 <= (sub.trial_end_date - today).days <= 7:
            reasons.append(f'Trial becomes paid on {sub.trial_end_date}.')
        if sub.cancel_by_date and 0 <= (sub.cancel_by_date - today).days <= 7:
            reasons.append(f'Cancellation deadline is {sub.cancel_by_date}.')
        duplicate = duplicates[(sub.team_id, sub.service_name.strip().casefold(), (sub.account_email or '').strip().casefold())]
        if len(duplicate) > 1 and sub.pk in duplicate:
            reasons.append('Multiple subscriptions use this service and account in the same workspace.')
        reviewed = sub.last_reviewed_on or sub.created_at.date()
        if reviewed <= today - relativedelta(months=6):
            reasons.append('No review in the last six months.')
        if sub.usage_rating in ('rarely', 'never'):
            reasons.append('Your last usage check suggests this is a saving opportunity.')
        if sub.cancellation_state == 'requested':
            reasons.append('Cancellation requested; provider confirmation is still needed.')
        future = [change for change in sub.price_changes.all() if change.effective_on > today]
        if future:
            change = future[0]
            current_price = sub.regular_price_on(today)
            annual_impact = monthly_equivalent(change.cost - current_price, sub.billing_cycle) * 12
            reasons.append(f'Price changes from {sub.currency} {current_price:.2f} to {change.cost:.2f} on {change.effective_on}. Annual rate impact: {sub.currency} {annual_impact:.2f}.')
        if reasons:
            items.append({'id': sub.pk, 'service': sub.service_name, 'currency': sub.currency, 'reasons': reasons,
                'monthly_saving': amount(monthly_equivalent(sub.share_on(today), sub.billing_cycle)) if sub.bills_on(today) else '0.00',
                'can_edit': sub.team_id is None or sub.team_id in owned})
    return Response({'items': items})


class ReviewAction(serializers.Serializer):
    action = serializers.ChoiceField(choices=['review', 'pause'])
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=100)
    usage_rating = serializers.ChoiceField(choices=['often', 'sometimes', 'rarely', 'never'], required=False)


@api_view(['POST'])
@transaction.atomic
def review_action(request):
    data = ReviewAction(data=request.data)
    data.is_valid(raise_exception=True)
    fields = data.validated_data
    subs = [_subscription_for(request.user, pk) for pk in set(fields['ids'])]
    for sub in subs:
        if fields['action'] == 'pause':
            sub.pause_from = timezone.localdate()
            sub.resume_on = None
            change_subscription_status(sub, actor=request.user, status='paused')
        else:
            sub.last_reviewed_on = timezone.localdate()
            sub.usage_rating = fields.get('usage_rating', sub.usage_rating)
            sub.save(update_fields=['last_reviewed_on', 'usage_rating'])
            from finance.permissions import log_activity
            log_activity(request.user, sub, 'subscription.reviewed', {'usage_rating': sub.usage_rating})
    return Response({'updated': len(subs)})


class PriceInput(serializers.Serializer):
    cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0'))
    effective_on = serializers.DateField()


@api_view(['GET', 'POST'])
@transaction.atomic
def price_changes(request, pk):
    sub = _subscription_for(request.user, pk)
    if request.method == 'POST':
        sub = Subscription.objects.select_for_update().get(pk=sub.pk)
        data = PriceInput(data=request.data)
        data.is_valid(raise_exception=True)
        fields = data.validated_data
        if sub.is_shared and sub.split_type == 'custom' and fields['cost'] < sum((p.share_amount or Decimal('0') for p in sub.participants.all()), Decimal('0')):
            raise serializers.ValidationError('The price cannot be lower than the fixed participant shares. Update the split first.')
        last = sub.price_changes.order_by('-effective_on').first()
        if fields['effective_on'] < timezone.localdate() or (last and fields['effective_on'] <= last.effective_on):
            raise serializers.ValidationError('Choose today or a later date after the last recorded price change.')
        PriceChange.objects.create(subscription=sub, previous_cost=sub.regular_price_on(fields['effective_on']), **fields)
        from finance.permissions import log_activity
        log_activity(request.user, sub, 'subscription.price.scheduled', {'cost': str(fields['cost']), 'effective_on': str(fields['effective_on'])})
    changes = []
    for change in sub.price_changes.all():
        # Older schedules can retain the original quote after an intervening price edit.
        previous_cost = changes[-1]['cost'] if changes else amount(change.previous_cost)
        changes.append({'id': change.pk, 'previous_cost': previous_cost,
                        'cost': amount(change.cost), 'effective_on': change.effective_on})
    return Response({'changes': changes}, status=201 if request.method == 'POST' else 200)


@api_view(['GET'])
def settlements(request):
    query = selection(request)
    charges = Transaction.objects.filter(payment_status='paid')
    if query['scope'] == 'personal':
        charges = charges.filter(user=request.user, team__isnull=True)
    else:
        charges = charges.filter(team__memberships__user=request.user)
    shares = ChargeShare.objects.filter(charge__in=charges).select_related('charge__user', 'charge__team', 'member').prefetch_related('repayments')
    groups = {}
    owners = set(request.user.team_memberships.filter(role__in=['owner', 'accountant']).values_list('team_id', flat=True))
    for share in shares:
        charge = share.charge
        key = (charge.team_id, charge.user_id, share.member_id or share.name.strip().casefold(), charge.currency)
        if key not in groups:
            groups[key] = {'debtor': share.member.email if share.member_id else share.name, 'creditor': charge.user.email,
                'team': charge.team.name if charge.team_id else None, 'currency': charge.currency, 'total': Decimal('0'), 'repaid': Decimal('0'), 'shares': []}
        row = groups[key]
        repaid = share.amount if share.reimbursed else share.repaid_amount
        row['total'] += share.amount
        row['repaid'] += repaid
        row['shares'].append({'id': share.pk, 'service': charge.service_name_snapshot, 'date': charge.charged_for_date,
            'outstanding': amount(share.amount - repaid), 'can_edit': charge.team_id is None or charge.team_id in owners,
            'repayments': [{'amount': amount(p.amount), 'note': p.note, 'date': p.created_at} for p in share.repayments.all()]})
    return Response({'balances': [{**row, 'total': amount(row['total']), 'repaid': amount(row['repaid']), 'outstanding': amount(row['total'] - row['repaid'])} for row in groups.values()]})


class RepaymentInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


@api_view(['POST'])
@transaction.atomic
def repay(request, pk):
    from dashboard.api_views import editable_charges
    share = get_object_or_404(ChargeShare.objects.select_for_update(), pk=pk, charge__in=editable_charges(request.user), charge__payment_status='paid')
    data = RepaymentInput(data=request.data)
    data.is_valid(raise_exception=True)
    value = data.validated_data['amount']
    if share.reimbursed or value > share.amount - share.repaid_amount:
        raise serializers.ValidationError('Repayment exceeds the outstanding share.')
    Repayment.objects.create(share=share, recorded_by=request.user, **data.validated_data)
    share.repaid_amount += value
    share.reimbursed = share.repaid_amount == share.amount
    share.save(update_fields=['repaid_amount', 'reimbursed'])
    if share.charge.subscription_id:
        from finance.permissions import log_activity
        log_activity(request.user, share.charge.subscription, 'repayment.recorded', {'share': share.pk, 'amount': str(value)})
    return Response({'outstanding': amount(share.amount - share.repaid_amount)}, status=201)
