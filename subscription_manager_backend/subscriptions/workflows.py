from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from accounts.models import TeamMembership
from accounts.services import is_team_owner

from .models import ReminderOffset, SubscriptionParticipant, TeamSubscriptionRequest
from .notifications import create_notification, create_team_notifications
from .services import record_due_charge_for_subscription


def sync_reminder_offsets(subscription, reminder_offsets):
    desired = set(reminder_offsets)
    current = set(subscription.offsets.values_list('days_before', flat=True))
    subscription.offsets.filter(days_before__in=current - desired).delete()
    ReminderOffset.objects.bulk_create([
        ReminderOffset(subscription=subscription, days_before=days)
        for days in sorted(desired - current)
    ])


def _prepare_participants(subscription, participants):
    if not subscription.is_shared:
        subscription.user_cost = subscription.cost
        return []
    if not participants:
        raise ValidationError('Please add at least one participant for shared subscriptions.')

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

    return [
        SubscriptionParticipant(subscription=subscription, name=participant['name'], share_amount=share)
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
    participants_to_create = _prepare_participants(subscription, participants)
    team = subscription.team
    if creating and team and not is_team_owner(actor, team):
        return _submit_team_request(subscription, actor, participants_to_create, reminder_offsets)

    with transaction.atomic():
        subscription.save()
        if not creating:
            subscription.participants.all().delete()
        SubscriptionParticipant.objects.bulk_create(participants_to_create)
        sync_reminder_offsets(subscription, reminder_offsets)
        if creating:
            record_due_charge_for_subscription(subscription)

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


def remove_subscription(subscription, *, actor):
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


def change_subscription_status(subscription, *, actor, status):
    subscription.status = status
    subscription.save(update_fields=['status', 'renewal_date', 'updated_at'])
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
