from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from finance.delivery import local_now
from finance.permissions import log_activity
from subscriptions.models import Subscription, TeamRenewal
from subscriptions.services import next_billing_date
from .models import Team, TeamMembership


ASSIGNABLE_ROLES = (TeamMembership.ROLE_OWNER, TeamMembership.ROLE_MEMBER)


def review_details(subscription, membership, today):
    review = getattr(subscription, 'renewal_review', None)
    day = next_billing_date(subscription, today)
    decision_is_current = day is not None and review is not None and review.decision_for == day
    assignee_id = review.assignee_id if review else None
    deadline = subscription.cancel_by_date
    due_on = day
    if deadline and day and deadline <= day:
        # An overdue cutoff belongs to this renewal until the billing cycle advances.
        if today <= deadline or (
            (not subscription.paid_through or deadline > subscription.paid_through)
            and subscription.calculate_renewal_date(today=deadline) == day
        ):
            due_on = deadline
    paid_seats = review.paid_seats if decision_is_current else None
    needed_seats = review.needed_seats if decision_is_current else None
    seat_savings = None
    if paid_seats and needed_seats is not None:
        unused_seats = max(0, paid_seats - needed_seats)
        estimate = subscription.price_on(day) * unused_seats / paid_seats
        seat_savings = format(estimate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')
    return {
        'assignee_id': assignee_id,
        'renewal_date': day,
        'due_on': due_on,
        'decision': review.decision if decision_is_current else '',
        'decided_at': review.decided_at if decision_is_current else None,
        'decided_by': review.decided_by.email if decision_is_current and review.decided_by else None,
        'paid_seats': paid_seats,
        'needed_seats': needed_seats,
        'seat_savings': seat_savings,
        'decision_reason': review.decision_reason if decision_is_current else '',
        'can_decide': day is not None and (
            membership.is_owner or (membership.pk == assignee_id and membership.role in ASSIGNABLE_ROLES)
        ),
    }


class RenewalUpdate(serializers.Serializer):
    assignee_id = serializers.IntegerField(min_value=1, allow_null=True, required=False)
    decision = serializers.ChoiceField(choices=TeamRenewal.Decision.choices, allow_blank=True, required=False)
    renewal_date = serializers.DateField(required=False)
    paid_seats = serializers.IntegerField(min_value=1, max_value=TeamRenewal.MAX_SEATS, allow_null=True, required=False)
    needed_seats = serializers.IntegerField(min_value=0, max_value=TeamRenewal.MAX_SEATS, allow_null=True, required=False)
    decision_reason = serializers.CharField(max_length=500, allow_blank=True, required=False)

    def validate(self, attrs):
        has_paid = 'paid_seats' in attrs
        has_needed = 'needed_seats' in attrs
        if has_paid != has_needed or (attrs.get('paid_seats') is None) != (attrs.get('needed_seats') is None):
            raise serializers.ValidationError('Enter both seat counts or leave both blank.')
        if (has_paid or 'decision_reason' in attrs) and 'decision' not in attrs:
            raise serializers.ValidationError('Choose a decision when recording seat counts or a reason.')
        if not attrs.get('decision') and (attrs.get('paid_seats') is not None or attrs.get('decision_reason')):
            raise serializers.ValidationError('Choose Keep, Change, or Cancel to record seat counts or a reason.')
        if 'decision' in attrs and 'renewal_date' not in attrs:
            raise serializers.ValidationError('Choose the renewal date for this decision.')
        if 'assignee_id' not in attrs and 'decision' not in attrs:
            raise serializers.ValidationError('Choose a renewal owner or a decision.')
        return attrs


@api_view(['PATCH'])
@transaction.atomic
def update_renewal(request, team_id, subscription_id):
    # Member role changes and renewal writes use the same team lock.
    team = get_object_or_404(Team.objects.select_for_update(), pk=team_id)
    member = get_object_or_404(TeamMembership.objects.select_for_update(), team=team, user=request.user)
    sub = get_object_or_404(Subscription.objects.select_for_update(), pk=subscription_id, team=team)
    fields = RenewalUpdate(data=request.data)
    fields.is_valid(raise_exception=True)
    values = fields.validated_data
    review, _ = TeamRenewal.objects.get_or_create(subscription=sub)
    today = local_now(request.user).date()
    changes = {}
    if 'assignee_id' in values:
        if not member.is_owner:
            raise PermissionDenied('Only a team owner can assign renewals.')
        target = values['assignee_id']
        if target is not None:
            get_object_or_404(TeamMembership.objects.select_for_update(), pk=target, team=team, role__in=ASSIGNABLE_ROLES)
        if review.assignee_id != target:
            changes['assignee'] = {'before': review.assignee_id, 'after': target}
            review.assignee_id = target
    if 'decision' in values:
        if not member.is_owner and (review.assignee_id != member.pk or member.role not in ASSIGNABLE_ROLES):
            raise PermissionDenied('Only a team owner or the assigned member can record the decision.')
        day = next_billing_date(sub, today)
        if values['renewal_date'] != day:
            raise serializers.ValidationError('The renewal date changed. Reload the team and review its current date.')
        decision = values['decision']
        is_current = review.decision_for == day
        previous = review.decision if is_current else ''
        previous_paid = review.paid_seats if is_current else None
        previous_needed = review.needed_seats if is_current else None
        previous_reason = review.decision_reason if is_current else ''
        paid_seats = values.get('paid_seats', previous_paid) if decision else None
        needed_seats = values.get('needed_seats', previous_needed) if decision else None
        reason = values.get('decision_reason', previous_reason) if decision else ''
        if previous != decision or (previous_paid, previous_needed, previous_reason) != (paid_seats, needed_seats, reason):
            changes.update(decision={'before': previous, 'after': decision}, renewal_date=day.isoformat())
            if (previous_paid, previous_needed) != (paid_seats, needed_seats):
                changes['seats'] = {'before': [previous_paid, previous_needed], 'after': [paid_seats, needed_seats]}
            if previous_reason != reason:
                # Keep the current explanation on the review, not in activity logs.
                changes['decision_reason'] = {'changed': True}
            review.decision = decision
            review.decision_for = day if decision else None
            review.decided_by = request.user if decision else None
            review.decided_at = timezone.now() if decision else None
            review.paid_seats = paid_seats
            review.needed_seats = needed_seats
            review.decision_reason = reason
    if changes:
        review.save()
        log_activity(request.user, sub, 'renewal.review.updated', changes)
    return Response(review_details(sub, member, today))
