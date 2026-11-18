from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.models import TeamMembership
from accounts.services import is_team_owner

from .models import ReminderOffset, SubscriptionParticipant, TeamSubscriptionRequest
from .notifications import create_notification, create_team_notifications
from .services import catch_up_charges, record_due_charge_for_subscription


def sync_reminder_offsets(subscription, reminder_offsets):
    desired = set(reminder_offsets)
    current = set(subscription.offsets.values_list('days_before', flat=True))
    subscription.offsets.filter(days_before__in=current - desired).delete()
    ReminderOffset.objects.bulk_create([
        ReminderOffset(subscription=subscription, days_before=days)
        for days in sorted(desired - current)
    ])


def prepare_participants(subscription, participants):
    if not subscription.is_shared:
        subscription.user_cost = subscription.cost
        return []
    if not participants:
        raise ValidationError('Please add at least one participant for shared subscriptions.')
    member_ids = [person.get('member_id') for person in participants if person.get('member_id')]
    allowed = set(TeamMembership.objects.filter(team_id=subscription.team_id).exclude(user_id=subscription.user_id).values_list('user_id', flat=True)) if subscription.team_id else set()
    if len(member_ids) != len(set(member_ids)) or not set(member_ids) <= allowed:
        raise ValidationError('Choose each participant from the current team once, excluding the payer.')

    if subscription.split_type == 'equal':
        cents, remainder = divmod(int(subscription.cost * 100), len(participants) + 1)
        subscription.user_cost = Decimal(cents + (remainder > 0)).scaleb(-2)
        shares = [
            Decimal(cents + (index < remainder)).scaleb(-2)
            for index in range(1, len(participants) + 1)
        ]
    else:
        shares = [participant['share'] for participant in participants]
        subscription.user_cost = subscription.cost - sum(shares, Decimal('0'))
        if subscription.user_cost < 0:
            raise ValidationError('The sum of participant shares exceeds the total cost.')
        if subscription.introductory_cost is not None and sum(shares, Decimal('0')) > subscription.introductory_cost:
            raise ValidationError('Fixed participant shares exceed the introductory price. Use an equal split or lower the shares.')
        if subscription.pk and subscription.price_changes.filter(effective_on__gte=timezone.localdate(), cost__lt=sum(shares, Decimal('0'))).exists():
            raise ValidationError('Fixed participant shares exceed a scheduled future price. Lower the shares first.')

    return [
        SubscriptionParticipant(subscription=subscription, name=participant['name'], share_amount=share, member_id=participant.get('member_id'))
        for participant, share in zip(participants, shares)
    ]


def _submit_team_request(subscription, actor, participants, reminder_offsets):
    team = subscription.team
    payload = {
        'service_name': subscription.service_name,
        'plan_name': subscription.plan_name,
        'category': subscription.category,
        'billing_cycle': subscription.billing_cycle,
        'display_color': subscription.display_color or '',
        'cost': str(subscription.cost),
        'user_cost': str(subscription.user_cost),
        'is_shared': bool(subscription.is_shared),
        'split_type': subscription.split_type,
        'currency': subscription.currency,
        'start_date': subscription.start_date.isoformat(),
        'trial_end_date': subscription.trial_end_date.isoformat() if subscription.trial_end_date else None,
        'cancel_by_date': subscription.cancel_by_date.isoformat() if subscription.cancel_by_date else None,
        'renewal_time': subscription.renewal_time.isoformat() if subscription.renewal_time else '',
        'status': subscription.status,
        'reminders_enabled': bool(subscription.reminders_enabled),
        'notes': subscription.notes or '',
        'account_email': subscription.account_email or '',
        'participants': [
            {'name': participant.name, 'share_amount': str(participant.share_amount)}
            for participant in participants
        ],
        'reminder_offsets': reminder_offsets,
    }
    for field in ('pause_from', 'resume_on', 'introductory_cost', 'introductory_until', 'cancellation_url', 'cancellation_state', 'cancellation_notes', 'access_until'):
        value = getattr(subscription, field)
        payload[field] = str(value) if value is not None else None
    for item, participant in zip(payload['participants'], participants):
        item['member_id'] = participant.member_id
    team_request = TeamSubscriptionRequest.objects.create(team=team, requested_by=actor, payload=payload)
    owners = team.memberships.select_related('user').filter(role=TeamMembership.ROLE_OWNER).exclude(user=actor)
    for owner in owners:
        create_notification(
            recipient=owner.user,
            actor=actor,
            team=team,
            event_type='team.request.submitted',
            title=f'New subscription request: {subscription.service_name}',
            body=f'{actor.email} submitted a request for {subscription.service_name}.',
            link_url=reverse('accounts:team_detail', args=[team.pk]),
            metadata={'request_id': team_request.pk},
            send_email_alert=True,
        )
    return team_request


def save_subscription(subscription, *, actor, participants, reminder_offsets):
    creating = subscription.pk is None
    from finance.permissions import team_permission, log_activity
    from finance.backup import SUB_FIELDS
    if subscription.team_id and not is_team_owner(actor, subscription.team):
        membership = TeamMembership.objects.filter(user=actor, team=subscription.team).first()
        if not creating or not membership or membership.role != 'member':
            raise ValidationError('Your team role does not allow subscription changes or requests.')
    before = {}
    before_participants = []
    before_offsets = []
    if not creating:
        previous_values = type(subscription).objects.get(pk=subscription.pk)
        before = {field: str(getattr(previous_values, field)) for field in SUB_FIELDS}
        before_participants = [{'name': p.name, 'share': str(p.share_amount), 'member_id': p.member_id} for p in previous_values.participants.all()]
        before_offsets = list(previous_values.offsets.values_list('days_before', flat=True))
    participants_to_create = prepare_participants(subscription, participants)
    team = subscription.team
    if creating and team and not is_team_owner(actor, team):
        return _submit_team_request(subscription, actor, participants_to_create, reminder_offsets)

    with transaction.atomic():
        if not creating:
            catch_up_charges(subscription.pk, timezone.localdate() - timedelta(days=1))
            from .models import PriceChange, Subscription
            previous = Subscription.objects.get(pk=subscription.pk)
            if previous.regular_price_on(timezone.localdate()) != subscription.cost:
                today = timezone.localdate()
                existing_change = previous.price_changes.filter(effective_on=today).first()
                PriceChange.objects.update_or_create(subscription=subscription, effective_on=today,
                    defaults={'previous_cost': existing_change.previous_cost if existing_change else previous.regular_price_on(today), 'cost': subscription.cost})
        subscription.save()
        if subscription.cancellation_state == 'confirmed' and subscription.status != 'cancelled':
            subscription.status = 'cancelled'
            subscription.save(update_fields=['status', 'updated_at'])
        if not creating:
            subscription.participants.all().delete()
        SubscriptionParticipant.objects.bulk_create(participants_to_create)
        sync_reminder_offsets(subscription, reminder_offsets)
        if creating:
            record_due_charge_for_subscription(subscription)
        changes = {field: {'before': before.get(field), 'after': str(getattr(subscription, field))} for field in SUB_FIELDS if before.get(field) != str(getattr(subscription, field))}
        # Credential values are never part of the change log.
        for field in ('notes', 'cancellation_notes'):
            if field in changes:
                changes[field] = {'changed': True}
        after_participants = [{'name': p.name, 'share': str(p.share_amount), 'member_id': p.member_id} for p in participants_to_create]
        if before_participants != after_participants:
            changes['participants'] = {'before': before_participants, 'after': after_participants}
        if sorted(before_offsets) != sorted(reminder_offsets):
            changes['reminder_offsets'] = {'before': before_offsets, 'after': reminder_offsets}
        log_activity(actor, subscription, 'subscription.created' if creating else 'subscription.updated', changes)

    if team:
        if creating:
            action, verb, prefix = 'created', 'added', 'New subscription added'
        else:
            action, verb, prefix = 'updated', 'updated', 'Subscription updated'
        create_team_notifications(
            team=team,
            actor=actor,
            subscription=subscription,
            event_type=f'subscription.{action}',
            title=f'{prefix}: {subscription.service_name}',
            body=f'{actor.email} {verb} {subscription.service_name}.',
            link_url=reverse('accounts:team_detail', args=[team.pk]),
            metadata={'subscription_id': subscription.pk},
            send_email_alert=True,
        )
    return None


@transaction.atomic
def remove_subscription(subscription, *, actor):
    from finance.permissions import log_activity
    log_activity(actor, subscription, 'subscription.deleted')
    catch_up_charges(subscription.pk, timezone.localdate() - timedelta(days=1))
    team = subscription.team
    service_name = subscription.service_name
    subscription.delete()
    if team:
        create_team_notifications(
            team=team,
            actor=actor,
            event_type='subscription.deleted',
            title=f'Subscription removed: {service_name}',
            body=f'{actor.email} removed {service_name}.',
            link_url=reverse('accounts:team_detail', args=[team.pk]),
            metadata={'service_name': service_name},
            send_email_alert=True,
        )


@transaction.atomic
def change_subscription_status(subscription, *, actor, status):
    from finance.permissions import log_activity
    before_status = subscription.status
    catch_up_charges(subscription.pk, timezone.localdate() - timedelta(days=1))
    if status == 'active':
        if subscription.status == 'paused':
            subscription.pause_from = None
            subscription.resume_on = None
        if subscription.status == 'cancelled':
            subscription.cancellation_state = 'none'
    subscription.status = status
    subscription.save(update_fields=['status', 'renewal_date', 'updated_at', 'pause_from', 'resume_on', 'cancellation_state'])
    log_activity(actor, subscription, 'subscription.status.changed', {'status': {'before': before_status, 'after': status}})
    if subscription.team_id:
        create_team_notifications(
            team=subscription.team,
            actor=actor,
            subscription=subscription,
            event_type='subscription.updated',
            title=f'Subscription updated: {subscription.service_name}',
            body=f'{actor.email} changed status to {status}.',
            link_url=reverse('accounts:team_detail', args=[subscription.team_id]),
            metadata={'subscription_id': subscription.pk, 'status': status},
            send_email_alert=True,
        )
