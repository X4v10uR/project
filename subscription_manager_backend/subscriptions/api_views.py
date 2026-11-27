import csv
from io import StringIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import prefetch_related_objects
from django.shortcuts import get_object_or_404
from django.utils import timezone
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
from .create_once import create_subscription_once
from .editing import StaleSubscriptionEdit, edit_revision
from .list_context import (
    _apply_subscription_card_metadata, _build_subscription_drawer_data,
    build_subscription_cards, build_subscription_list_context,
)
from .services import next_billing_date
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
            expected_revision=request.headers.get('If-Match', '').strip('"') if 'If-Match' in request.headers else None,
        )
    except StaleSubscriptionEdit as exc:
        return Response({'detail': str(exc), 'code': 'stale_subscription'}, status=status.HTTP_412_PRECONDITION_FAILED)
    except ValidationError as exc:
        errors = exc.message_dict if hasattr(exc, 'error_dict') else {'participants': exc.messages}
        raise serializers.ValidationError(errors) from exc
    if pending:
        return Response({'request_id': pending.pk, 'team': team.pk}, status=status.HTTP_202_ACCEPTED)
    if request.data.get('account_password'):
        audit(request.user, 'credentials.updated', f'Subscription {subscription.pk}')
        from finance.permissions import log_activity
        log_activity(request.user, subscription, 'credentials.updated')
    subscription.refresh_from_db()
    return Response(
        SubscriptionSerializer(subscription).data,
        status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED,
    )


@api_view(['GET', 'POST'])
def subscriptions(request):
    if request.method == 'POST':
        return create_subscription_once(request, _write_subscription, _replay_subscription_creation)
    page_number = request.query_params.get('page')
    if page_number is not None:
        try:
            page_number = max(int(page_number), 1)
        except ValueError:
            page_number = 1
    context = build_subscription_list_context(request, page_number=page_number)
    if page_number is not None:
        page = context['page']
        return Response({
            'subscriptions': build_subscription_cards(context['subscriptions']),
            'stats': context['subscriptions_stats'],
            'burn_metrics': context['subscriptions_burn_metrics'],
            'pagination': {
                'page': page.number, 'pages': page.paginator.num_pages, 'count': page.paginator.count,
                'start': page.start_index(), 'end': page.end_index(),
            },
        })
    prefetch_related_objects(context['subscriptions'], 'participants', 'offsets')
    return Response({
        'subscriptions': SubscriptionSerializer(context['subscriptions'], many=True).data,
        'stats': context['subscriptions_stats'],
        'burn_metrics': context['subscriptions_burn_metrics'],
        'details': context['subscription_drawer_data'],
    })


def _replay_subscription_creation(request, receipt):
    if receipt.response_status == status.HTTP_201_CREATED and receipt.subscription_id:
        subscription = _subscription_for(request.user, receipt.subscription_id)
        payload = SubscriptionSerializer(subscription).data
    elif receipt.response_status == status.HTTP_202_ACCEPTED and receipt.team_request_id:
        pending = receipt.team_request
        _team_for(request.user, pending.team_id)
        payload = {'request_id': pending.pk, 'team': pending.team_id}
    else:
        return Response(
            {'code': 'idempotency_result_unavailable',
             'detail': 'The result of this save is no longer available. Check your subscriptions before submitting again.'},
            status=status.HTTP_410_GONE,
        )
    return Response(payload, status=receipt.response_status, headers={'Idempotency-Replayed': 'true'})


@api_view(['GET', 'PUT', 'DELETE'])
def subscription_detail(request, pk):
    if request.method == 'PUT':
        with transaction.atomic():
            subscription = _subscription_for(request.user, pk)
            subscription = Subscription.objects.select_for_update().get(pk=subscription.pk)
            return _write_subscription(request, subscription)
    subscription = _subscription_for(request.user, pk)
    if request.method == 'DELETE':
        remove_subscription(subscription, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    prefetch_related_objects([subscription], 'price_changes', 'participants', 'offsets')
    subscription.next_payment_date = next_billing_date(subscription, timezone.localdate())
    _apply_subscription_card_metadata([subscription])
    details = _build_subscription_drawer_data([subscription])[str(subscription.pk)]
    from finance.delivery import local_now
    next_payment = next_billing_date(subscription, local_now(request.user).date())
    return Response({**SubscriptionSerializer(subscription).data, 'details': details, 'edit_revision': edit_revision(subscription),
                     'next_payment': {'date': next_payment, 'amount': str(subscription.price_on(next_payment))}
                     if next_payment else None})


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
