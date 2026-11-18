import csv
from io import StringIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import prefetch_related_objects
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.exceptions import NotFound
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response

from accounts.models import TeamMembership
from accounts.services import is_team_owner
from accounts.security import audit, require_recent

from .api_serializers import SubscriptionInput, SubscriptionSerializer, SubscriptionStatusInput, subscription_form
from .cards_state import build_card_options
from .color_utils import LIGHT_SUBSCRIPTION_COLOR_PRESETS
from .list_context import _apply_subscription_card_metadata, _build_subscription_drawer_data, build_subscription_list_context
from .models import Subscription
from .views import (
    CATEGORY_SUGGESTIONS,
    _build_subscription_prefill,
    _get_accessible_subscription,
    build_subscription_csv,
)
from .workflows import change_subscription_status, remove_subscription, save_subscription


def _team_for(user, team_id):
    if not team_id:
        return None
    membership = get_object_or_404(
        TeamMembership.objects.select_related('team'), user=user, team_id=team_id
    )
    return membership.team


def _subscription_for(user, pk):
    subscription = _get_accessible_subscription(user, pk, require_owner=True)
    if subscription is None:
        raise NotFound()
    return subscription


def _write_subscription(request, instance=None):
    payload = SubscriptionInput(data=request.data)
    payload.is_valid(raise_exception=True)
    data = payload.validated_data
    team = instance.team if instance else _team_for(request.user, data.get('team_id'))
    form = subscription_form(request.data, user=request.user, instance=instance)
    subscription = form.save(commit=False)
    if instance is None:
        subscription.user = request.user
        subscription.team = team
    if request.data.get('account_password'):
        subscription.set_account_password(form.cleaned_data['account_password'])
    try:
        pending = save_subscription(
            subscription,
            actor=request.user,
            participants=data['participants'],
            reminder_offsets=data['reminder_offsets'],
        )
    except ValidationError as exc:
        raise serializers.ValidationError({'participants': exc.messages}) from exc
    if pending:
        return Response({'request_id': pending.pk, 'team': team.pk}, status=status.HTTP_202_ACCEPTED)
    if request.data.get('account_password'):
        audit(request.user, 'credentials.updated', f'Subscription {subscription.pk}')
    subscription.refresh_from_db()
    return Response(
        SubscriptionSerializer(subscription).data,
        status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED,
    )


@api_view(['GET', 'POST'])
def subscriptions(request):
    if request.method == 'POST':
        return _write_subscription(request)
    context = build_subscription_list_context(request)
    prefetch_related_objects(context['subscriptions'], 'participants', 'offsets')
    return Response({
        'subscriptions': SubscriptionSerializer(context['subscriptions'], many=True).data,
        'stats': context['subscriptions_stats'],
        'burn_metrics': context['subscriptions_burn_metrics'],
        'details': context['subscription_drawer_data'],
    })


@api_view(['GET', 'PUT', 'DELETE'])
def subscription_detail(request, pk):
    subscription = _subscription_for(request.user, pk)
    if request.method == 'PUT':
        return _write_subscription(request, subscription)
    if request.method == 'DELETE':
        remove_subscription(subscription, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    subscription.participant_count = subscription.participants.count()
    _apply_subscription_card_metadata([subscription])
    details = _build_subscription_drawer_data([subscription])[str(subscription.pk)]
    return Response({**SubscriptionSerializer(subscription).data, 'details': details})


@api_view(['POST'])
def subscription_status(request, pk):
    subscription = _subscription_for(request.user, pk)
    payload = SubscriptionStatusInput(data=request.data)
    payload.is_valid(raise_exception=True)
    new_status = payload.validated_data['status']
    change_subscription_status(subscription, actor=request.user, status=new_status)
    return Response({'status': new_status})


@api_view(['POST'])
def subscription_password(request, pk):
    subscription = _subscription_for(request.user, pk)
    require_recent(request)
    password = subscription.get_account_password()
    if password is None:
        raise NotFound('Password unavailable.')
    audit(request.user, 'credentials.revealed', f'Subscription {pk}')
    return Response({'password': password}, headers={'Cache-Control': 'no-store'})


@api_view(['GET'])
def subscription_options(request):
    team_id = request.query_params.get('team')
    team = _team_for(request.user, serializers.IntegerField(min_value=1).run_validation(team_id)) if team_id else None
    return Response({
        'cards': build_card_options(request.user),
        'statuses': Subscription.STATUS_CHOICES,
        'cycles': Subscription.BILLING_CYCLE_CHOICES,
        'categories': CATEGORY_SUGGESTIONS,
        'default_reminder_offset': settings.NOTIFICATION_DAYS_BEFORE,
        'colors': LIGHT_SUBSCRIPTION_COLOR_PRESETS,
        'prefill': _build_subscription_prefill(request.query_params),
        'team': {'id': team.pk, 'name': team.name, 'can_create': is_team_owner(request.user, team)} if team else None,
        'members': [{'user_id': member.user_id, 'email': member.user.email} for member in team.memberships.select_related('user')] if team else [],
    })


class CSVStatusRenderer(BaseRenderer):
    """Render DRF errors and metadata for clients requesting the CSV attachment."""

    media_type = 'text/csv'
    format = 'csv'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        output = StringIO()
        csv.writer(output).writerows((data.keys(), data.values()))
        return output.getvalue()


@api_view(['GET'])
@renderer_classes([JSONRenderer, CSVStatusRenderer])
def subscription_export(request):
    return build_subscription_csv(request)
