from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from subscriptions.models import InAppNotification
from subscriptions.notifications import (
    notification_unread_count,
    push_bulk_read,
    push_updated,
    serialize_notification,
)
from subly.context_processors import runtime_flags

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
    charges = charges_for_scope(request.user, filters['scope']).select_related('team')
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
         'team': row.team.name if row.team_id else None, 'subscription_id': row.subscription_id}
        for row in rows
    ])
    totals = charges.order_by().values('currency').annotate(total=Sum('amount'))
    response.data['totals_by_currency'] = {
        row['currency']: format(row['total'], '.2f') for row in totals
    }
    return response


class BalanceTargetSerializer(serializers.Serializer):
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
    data = build_dashboard_view_model(request.user, scope=request.query_params.get('scope'))
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
    snapshot = set_user_balance_target(request.user, serializer.validated_data['target_balance'], scope=scope)
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
