from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.utils.urls import remove_query_param, replace_query_param

from subscriptions.models import ChargeShare, InAppNotification, Repayment, Transaction
from subscriptions.notifications import (
    mark_all_notifications_read,
    notification_unread_count,
    push_updated,
    recent_notifications,
    serialize_notification,
)
from subly.context_processors import runtime_flags

from .attention import needs_attention
from .budgets import check_budget
from .models import BalanceAdjustment
from .services import VALID_DASHBOARD_SCOPES, build_dashboard_view_model, charges_for_scope, set_user_balance_target


class ChargeFilters(serializers.Serializer):
    charge = serializers.IntegerField(min_value=1, required=False)
    scope = serializers.ChoiceField(choices=sorted(VALID_DASHBOARD_SCOPES), default='personal')
    service = serializers.CharField(required=False, max_length=100, allow_blank=True)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, data):
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise serializers.ValidationError({'end': 'Choose an end date on or after the start date.'})
        return data


class HistoryCursor(serializers.Serializer):
    cursor_direction = serializers.ChoiceField(choices=('older', 'newer'), required=False)
    cursor_date = serializers.DateField(required=False)
    cursor_id = serializers.IntegerField(min_value=1, required=False)

    def validate(self, data):
        if data and len(data) != 3:
            raise serializers.ValidationError('Incomplete charge history cursor.')
        return data


def _history_before(day, pk):
    return Q(charged_for_date__lt=day) | Q(charged_for_date=day, pk__lt=pk)


def _history_after(day, pk):
    return Q(charged_for_date__gt=day) | Q(charged_for_date=day, pk__gt=pk)


def _history_page(request, charges):
    cursor = HistoryCursor(data=request.query_params)
    cursor.is_valid(raise_exception=True)
    fields = cursor.validated_data
    if not fields and 'page' in request.query_params:
        # Bookmarked legacy page numbers remain readable. New navigation uses cursors.
        pages = PageNumberPagination()
        pages.page_size = 50
        rows = pages.paginate_queryset(charges.order_by('-charged_for_date', '-pk'), request)
        return rows, pages.get_previous_link(), pages.get_next_link()
    ordered = charges.order_by('-charged_for_date', '-pk')
    if fields:
        day, pk = fields['cursor_date'], fields['cursor_id']
        if fields['cursor_direction'] == 'older':
            ordered = ordered.filter(_history_before(day, pk))
        else:
            ordered = ordered.filter(_history_after(day, pk)).reverse()
    rows = list(ordered[:50])
    if fields.get('cursor_direction') == 'newer':
        rows.reverse()

    def link(direction, row):
        url = remove_query_param(request.build_absolute_uri(), 'page')
        url = replace_query_param(url, 'cursor_direction', direction)
        url = replace_query_param(url, 'cursor_date', row.charged_for_date.isoformat())
        return replace_query_param(url, 'cursor_id', row.pk)

    if not rows:
        # A concurrent delete can empty a cursor page; offer a first-page recovery.
        first = request.build_absolute_uri()
        for name in ('page', 'cursor_direction', 'cursor_date', 'cursor_id'):
            first = remove_query_param(first, name)
        return rows, first if fields and charges.exists() else None, None
    head, tail = rows[0], rows[-1]
    previous = link('newer', head) if fields and charges.filter(_history_after(head.charged_for_date, head.pk)).exists() else None
    next_link = link('older', tail) if charges.filter(_history_before(tail.charged_for_date, tail.pk)).exists() else None
    return rows, previous, next_link


@api_view(['GET'])
def charge_history(request):
    query = ChargeFilters(data=request.query_params)
    query.is_valid(raise_exception=True)
    filters = query.validated_data
    shares = ChargeShare.objects.annotate(has_repayments=Exists(Repayment.objects.filter(share_id=OuterRef('pk'))))
    charges = charges_for_scope(request.user, filters['scope']).select_related('team').prefetch_related(
        Prefetch('shares', queryset=shares)
    )
    if 'charge' in filters:
        charges = charges.filter(pk=filters['charge'])
    owned_teams = set(request.user.team_memberships.filter(role__in=['owner', 'accountant']).values_list('team_id', flat=True))
    if filters.get('service'):
        charges = charges.filter(service_name_snapshot__icontains=filters['service'])
    if filters.get('start'):
        charges = charges.filter(charged_for_date__gte=filters['start'])
    if filters.get('end'):
        charges = charges.filter(charged_for_date__lte=filters['end'])
    rows, previous, next_link = _history_page(request, charges)
    results = [
        {'id': row.pk, 'service': row.service_name_snapshot, 'date': row.charged_for_date,
         'amount': str(row.amount), 'currency': row.currency, 'source': row.source,
         'shares_captured': row.shares_captured, 'payment_status': row.payment_status, 'can_edit': row.team_id is None or row.team_id in owned_teams,
         'shares': [{'id': share.pk, 'name': share.name, 'amount': str(share.amount), 'reimbursed': share.reimbursed, 'has_repayments': share.has_repayments}
                    for share in row.shares.all()],
         'team': row.team.name if row.team_id else None, 'subscription_id': row.subscription_id}
        for row in rows
    ]
    totals = list(charges.order_by().values('currency').annotate(
        count=Count('pk'), total=Sum('amount'), paid=Sum('amount', filter=Q(payment_status='paid')),
    ))
    return Response({'results': results, 'previous': previous, 'next': next_link,
                     'count': sum(row['count'] for row in totals),
                     'totals_by_currency': {row['currency']: format(row['total'], '.2f') for row in totals},
                     'paid_by_currency': {row['currency']: format(row['paid'], '.2f') for row in totals if row['paid'] is not None}})


def editable_charges(user):
    return Transaction.objects.filter(
        Q(user=user, team__isnull=True) |
        Q(team__memberships__user=user, team__memberships__role__in=['owner', 'accountant'])
    )


class PaymentUpdate(serializers.Serializer):
    payment_status = serializers.ChoiceField(choices=Transaction.PaymentStatus.choices)


@api_view(['PATCH'])
@transaction.atomic
def charge_payment(request, pk):
    charge = get_object_or_404(editable_charges(request.user).select_for_update(of=('self',)), pk=pk)
    data = PaymentUpdate(data=request.data)
    data.is_valid(raise_exception=True)
    status = data.validated_data['payment_status']
    if charge.payment_status == status:
        return Response({'payment_status': status})
    charge.payment_status = status
    charge.save(update_fields=['payment_status'])
    if charge.subscription_id:
        from finance.permissions import log_activity
        log_activity(request.user, charge.subscription, 'payment.status.changed', {'charge': charge.pk, 'status': charge.payment_status})
    return Response({'payment_status': charge.payment_status})


class HistoricalShare(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))


@api_view(['POST'])
@transaction.atomic
def historical_share(request, pk):
    charge = get_object_or_404(editable_charges(request.user).select_for_update(of=('self',)), pk=pk)
    if charge.shares_captured:
        raise serializers.ValidationError('This charge already has its original split.')
    data = HistoricalShare(data=request.data)
    data.is_valid(raise_exception=True)
    name = data.validated_data['name']
    amount = data.validated_data['amount']
    share, created = charge.shares.get_or_create(name=name, defaults={'amount': amount})
    if share.amount != amount:
        raise serializers.ValidationError({'name': 'A different share is already recorded for this name.'})
    if created and charge.subscription_id:
        from finance.permissions import log_activity
        log_activity(request.user, charge.subscription, 'share.historical.added', {'name': name, 'amount': str(amount)})
    return Response({'id': share.pk}, status=201 if created else 200)


class ReimbursementUpdate(serializers.Serializer):
    reimbursed = serializers.BooleanField(required=True)


@api_view(['PATCH'])
@transaction.atomic
def charge_share(request, pk, share_id):
    share = get_object_or_404(ChargeShare.objects.select_for_update(), charge__in=editable_charges(request.user), charge_id=pk, pk=share_id)
    data = ReimbursementUpdate(data=request.data)
    data.is_valid(raise_exception=True)
    if share.repayments.exists():
        raise serializers.ValidationError('This share has repayment records. Manage it under Settlements.')
    reimbursed = data.validated_data['reimbursed']
    if share.reimbursed == reimbursed:
        return Response({'reimbursed': reimbursed})
    share.reimbursed = reimbursed
    share.save(update_fields=['reimbursed'])
    if share.charge.subscription_id:
        from finance.permissions import log_activity
        log_activity(request.user, share.charge.subscription, 'share.reimbursement.changed', {'share': share.pk, 'reimbursed': share.reimbursed})
    return Response({'reimbursed': share.reimbursed})


class CurrencySelection(serializers.Serializer):
    currency = serializers.RegexField(r'^[A-Za-z]{3}$', required=False)

    def validate_currency(self, value):
        return value.upper()


class BudgetInput(CurrencySelection):
    scope = serializers.ChoiceField(choices=sorted(VALID_DASHBOARD_SCOPES), default='personal')
    monthly_limit = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), allow_null=True)


@api_view(['PUT'])
@transaction.atomic
def budget(request):
    data = BudgetInput(data=request.data)
    data.is_valid(raise_exception=True)
    fields = data.validated_data
    amount = fields.pop('monthly_limit')
    fields.setdefault('currency', 'USD')
    defaults = {'monthly_limit': amount}
    if amount is None:
        defaults['over_budget'] = False
    row, _ = BalanceAdjustment.objects.update_or_create(user=request.user, **fields, defaults=defaults)
    check_budget(row.pk)
    return Response(status=204)


class BalanceTargetSerializer(CurrencySelection):
    target_balance = serializers.DecimalField(
        max_digits=None,
        decimal_places=None,
        min_value=Decimal('-1000000'),
        max_value=Decimal('1000000'),
    )
    scope = serializers.CharField(required=False, allow_blank=True)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_data(request):
    selection = CurrencySelection(data=request.query_params)
    selection.is_valid(raise_exception=True)
    preview = request.query_params.get('preview') == '1'
    data = build_dashboard_view_model(request.user, scope=request.query_params.get('scope'),
                                      selected_currency=selection.validated_data.get('currency'), preview=preview)
    team_names = list(request.user.team_memberships.order_by('team__name').values_list('team__name', flat=True)[:2])
    data['team_label'] = team_names[0] if len(team_names) == 1 else ('All teams' if team_names else '')
    data['show_get_started'] = (
        data['dashboard_scope'] == 'personal' and not any(data[key] for key in ('total_active', 'total_paused', 'total_cancelled'))
        and not team_names
    )
    attention = needs_attention(request.user, data['dashboard_scope'])
    data['needs_attention_count'] = len(attention)
    data['needs_attention'] = attention[:25] if preview else attention
    data['upcoming_count'] = len(data.pop('upcoming_renewals'))
    for name in ('active_subscriptions', 'paused_subscriptions', 'cancelled_subscriptions', 'shared_subscriptions'):
        data.pop(name)
    data['monthly_spend_by_currency'] = {
        currency: str(amount) for currency, amount in data['monthly_spend_by_currency'].items()
    }
    for name in ('monthly_spend', 'yearly_spend', 'avg_monthly_spend'):
        data[name] = str(data[name])
    return Response(data)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def adjust_balance(request):
    serializer = BalanceTargetSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    scope = (serializer.validated_data.get('scope') or request.query_params.get('scope') or 'personal').strip().lower()
    if scope not in VALID_DASHBOARD_SCOPES:
        raise serializers.ValidationError({'scope': ['Choose personal or teams.']})
    snapshot = set_user_balance_target(request.user, serializer.validated_data['target_balance'], scope=scope,
                                       currency=serializer.validated_data.get('currency', 'USD'))
    return Response(snapshot)


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def notifications(request):
    paginator = PageNumberPagination()
    paginator.page_size = 50
    recent = paginator.paginate_queryset(recent_notifications(request.user), request)
    return Response({
        'notifications': [serialize_notification(notification) for notification in recent],
        'next': paginator.get_next_link(),
        'unread_count': notification_unread_count(request.user),
        **runtime_flags(request),
    })


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def unread_count(request):
    return Response({'unread_count': notification_unread_count(request.user)})


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def mark_read(request, pk):
    notification = get_object_or_404(InAppNotification, recipient=request.user, pk=pk)
    if not notification.is_read:
        notification.mark_read()
        push_updated(notification)
    return Response({'unread_count': notification_unread_count(request.user)})


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def mark_all_read(request):
    mark_all_notifications_read(request.user)
    return Response({'unread_count': notification_unread_count(request.user)})
