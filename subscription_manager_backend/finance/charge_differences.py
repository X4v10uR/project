"""Review differences between confirmed bank payments and recorded charges."""

from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from subscriptions.models import Transaction

from .models import ImportedPayment


def eligible_payments(user):
    # A match must not share the importing member's private bank amount with
    # other members. Require the original match permissions in the team as well.
    return ImportedPayment.objects.filter(
        Q(charge__team__isnull=True, charge__user=user) |
        Q(charge__team__memberships__user=user,
          charge__team__memberships__role__in=['owner', 'accountant']),
        connection__user=user, connection__provider='statement',
        pending=False, removed=False, dismissed=False, amount__gt=0,
        charge__payment_status=Transaction.PaymentStatus.PAID,
        currency=F('charge__currency'),
    ).select_related('charge__subscription', 'charge__team').prefetch_related('charge__shares')


def difference_for(payment):
    charge = payment.charge
    shares = list(charge.shares.all())
    if not charge.shares_captured and (shares or (charge.subscription and charge.subscription.is_shared)):
        # A legacy split may not have a complete snapshot of the full bill.
        return None
    # Transaction.amount is the payer's share. A bank payment reflects the
    # full provider bill, so add the share snapshots, not today's split.
    expected = charge.amount + sum((share.amount for share in shares), Decimal('0'))
    return expected, payment.amount - expected


def attention_items(user, scope):
    result = []
    personal = scope == 'personal'
    owned_teams = (set() if personal else set(
        user.team_memberships.filter(role='owner').values_list('team_id', flat=True)
    ))
    for payment in eligible_payments(user).filter(charge__team__isnull=personal):
        amounts = difference_for(payment)
        if amounts is None:
            continue
        expected, delta = amounts
        if not delta or delta == payment.acknowledged_charge_difference:
            continue
        charge = payment.charge
        sub = charge.subscription
        can_edit = (sub is not None and sub.team_id == charge.team_id and
                    ((sub.user_id == user.pk) if personal else sub.team_id in owned_teams))
        result.append({
            'id': f'charge-difference-{payment.pk}', 'kind': 'charge_difference',
            'service': charge.service_name_snapshot, 'workspace': charge.team.name if charge.team_id else None,
            'date': payment.paid_on, 'amount': str(payment.amount), 'currency': payment.currency,
            'action': 'Review charge', 'url': f'/dashboard/history/?scope={scope}&charge={charge.pk}',
            'difference': {
                'payment_id': payment.pk, 'expected': str(expected), 'delta': str(delta),
                'price_url': f'/subscriptions/{sub.pk}/edit/#price-history' if can_edit else None,
            },
        })
    return result


class DismissInput(serializers.Serializer):
    delta = serializers.DecimalField(max_digits=13, decimal_places=2)


@api_view(['POST'])
@transaction.atomic
def dismiss(request, pk):
    data = DismissInput(data=request.data)
    data.is_valid(raise_exception=True)
    payment = get_object_or_404(eligible_payments(request.user).select_for_update(of=('self',)), pk=pk)
    amounts = difference_for(payment)
    if amounts is None or not amounts[1]:
        raise Http404
    if amounts[1] != data.validated_data['delta']:
        raise ValidationError('This payment amount changed. Reload the dashboard before dismissing it.')
    payment.acknowledged_charge_difference = amounts[1]
    payment.save(update_fields=['acknowledged_charge_difference'])
    return Response({'saved': True})
