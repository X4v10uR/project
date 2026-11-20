from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from accounts.models import TeamMembership
from subscriptions.models import Subscription, Transaction


def team_permission(user, team_id, permission):
    if team_id is None:
        return True
    member = TeamMembership.objects.filter(user=user, team_id=team_id).first()
    if member is None:
        return False
    if permission == 'read':
        return True
    if permission == 'finance':
        return member.role in ('owner', 'accountant', 'member')
    if permission == 'pay':
        return member.role in ('owner', 'accountant')
    if permission == 'credentials':
        return member.may_view_credentials
    return member.role == 'owner'


def require_team(user, team_id, permission):
    if not team_permission(user, team_id, permission):
        raise PermissionDenied('Your team role does not allow this action.')


def subscriptions_for(user):
    return Subscription.objects.filter(Q(user=user, team__isnull=True) | Q(team__memberships__user=user)).distinct()


def charges_for(user):
    return Transaction.objects.filter(Q(user=user, team__isnull=True) | Q(team__memberships__user=user)).distinct()


def subscription_for(user, pk, permission='read'):
    sub = get_object_or_404(subscriptions_for(user), pk=pk)
    require_team(user, sub.team_id, permission)
    return sub


def log_activity(actor, sub, action, changes=None):
    from .models import Activity
    return Activity.objects.create(user=actor, owner=sub.user, team=sub.team, subscription=sub,
        service=sub.service_name, action=action, changes=changes or {})
