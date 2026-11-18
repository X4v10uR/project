from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from accounts.models import TeamMembership
from subscriptions.models import ChargeShare, InAppNotification, Transaction
from subscriptions.notifications import (
    notification_unread_count,
    push_bulk_read,
    push_updated,
    serialize_notification,
)
from subly.context_processors import runtime_flags

from .budgets import check_budget
from .models import BalanceAdjustment
from .services import VALID_DASHBOARD_SCOPES, build_dashboard_view_model, charges_for_scope, set_user_balance_target


class ChargeFilters(serializers.Serializer):
    scope = serializers.ChoiceField(choices=sorted(VALID_DASHBOARD_SCOPES), default='personal')
    service = serializers.CharField(required=False, max_length=100, allow_blank=True)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)

    def validate(self, data):
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise serializers.ValidationError({'end': 'Choose an end date on or after the start date.'})
        return data


@api_view(['GET'])
def charge_history(request):
    query = ChargeFilters(data=request.query_params)
    query.is_valid(raise_exception=True)
    filters = query.validated_data
    charges = charges_for_scope(request.user, filters['scope']).select_related('team').prefetch_related('shares')
    owned_teams = set(request.user.team_memberships.filter(role=TeamMembership.ROLE_OWNER).values_list('team_id', flat=True))
    if filters.get('service'):
        charges = charges.filter(service_name_snapshot__icontains=filters['service'])
    if filters.get('start'):
        charges = charges.filter(charged_for_date__gte=filters['start'])
    if filters.get('end'):
        charges = charges.filter(charged_for_date__lte=filters['end'])
    pages = PageNumberPagination()
    pages.page_size = 50
    rows = pages.paginate_queryset(charges.order_by('-charged_for_date', '-pk'), request)
    response = pages.get_paginated_response([
        {'id': row.pk, 'service': row.service_name_snapshot, 'date': row.charged_for_date,
         'amount': str(row.amount), 'currency': row.currency, 'source': row.source,
         'shares_captured': row.shares_captured, 'payment_status': row.payment_status, 'can_edit': row.team_id is None or row.team_id in owned_teams,
         'shares': [{'id': share.pk, 'name': share.name, 'amount': str(share.amount), 'reimbursed': share.reimbursed, 'has_repayments': share.repayments.exists()}
                    for share in row.shares.all()],
         'team': row.team.name if row.team_id else None, 'subscription_id': row.subscription_id}
        for row in rows
    ])
    totals = charges.order_by().values('currency').annotate(total=Sum('amount'), paid=Sum('amount', filter=Q(payment_status='paid')))
    response.data['totals_by_currency'] = {
        row['currency']: format(row['total'], '.2f') for row in totals
    }
    response.data['paid_by_currency'] = {row['currency']: format(row['paid'], '.2f') for row in totals if row['paid'] is not None}
    return response


def editable_charges(user):
    return Transaction.objects.filter(
        Q(user=user, team__isnull=True) |
        Q(team__memberships__user=user, team__memberships__role=TeamMembership.ROLE_OWNER)
    )


class PaymentUpdate(serializers.Serializer):
    payment_status = serializers.ChoiceField(choices=Transaction.PaymentStatus.choices)


@api_view(['PATCH'])
def charge_payment(request, pk):
    charge = get_object_or_404(editable_charges(request.user), pk=pk)
    data = PaymentUpdate(data=request.data)
    data.is_valid(raise_exception=True)
    charge.payment_status = data.validated_data['payment_status']
    charge.save(update_fields=['payment_status'])
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
    share.reimbursed = data.validated_data['reimbursed']
    share.save(update_fields=['reimbursed'])
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
    data = build_dashboard_view_model(request.user, scope=request.query_params.get('scope'),
                                      selected_currency=selection.validated_data.get('currency'))
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
    recent = InAppNotification.objects.filter(recipient=request.user).select_related('team')[:50]
    return Response({
        'notifications': [serialize_notification(notification) for notification in recent],
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
    unread = InAppNotification.objects.filter(recipient=request.user, is_read=False)
    if unread.update(is_read=True, read_at=timezone.now()):
        push_bulk_read(request.user)
    return Response({'unread_count': notification_unread_count(request.user)})
