import logging
from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from subscriptions.models import InAppNotification, ReminderOffset, Subscription, SubscriptionParticipant, TeamSubscriptionRequest, Transaction
from subscriptions.money import monthly_equivalent
from subscriptions.notifications import create_notification, create_team_notifications
from subscriptions.services import record_due_charge_for_subscription

from .models import Team, TeamInvite, TeamMembership, User
from .forms import CustomUserCreationForm
from .services import accept_invite, create_team_invite, invite_accept_url, is_team_owner, user_team_membership

logger = logging.getLogger(__name__)


class TeamActionError(Exception):
    def __init__(self, message, *, status_code=400):
        super().__init__(message)
        self.status_code = status_code

TEAM_ACCENT_PALETTE = (
    "#E8F542",
    "#7ECDC4",
    "#C5B8F5",
    "#F7D9A0",
    "#A9D8F7",
    "#F5B8D8",
)

def invite_status(invite):
    if invite.accepted_at:
        return 'already_used'
    if invite.revoked_at:
        return 'revoked'
    if invite.is_expired():
        return 'expired'
    return 'ready'


def invite_access_status(invite, user):
    if not invite:
        return 'invalid'
    status = invite_status(invite)
    if status != 'ready':
        return status
    if user.is_authenticated:
        return 'ready' if user.email.lower() == invite.email.lower() else 'email_mismatch'
    if User.objects.filter(email__iexact=invite.email).exists():
        return 'sign_in_required'
    return 'ready'


@transaction.atomic
def redeem_invite(*, user, token=None, signup_data=None, received_invite_id=None):
    if received_invite_id is not None:
        invites = received_team_invites(user).filter(pk=received_invite_id)
    else:
        invites = TeamInvite.objects.filter(token_hash=TeamInvite.hash_token(token))
    team_id = invites.values_list('team_id', flat=True).first()
    # Match the lock order used by invite rotation.
    if team_id is None or not Team.objects.select_for_update().filter(pk=team_id).exists():
        return {'result': 'invalid', 'invite': None}
    invite = invites.select_for_update().select_related('team').first()
    status = invite_access_status(invite, user)
    if status != 'ready':
        return {'result': status, 'invite': invite}

    if not user.is_authenticated:
        password = make_password(None)
        if signup_data is not None:
            form = CustomUserCreationForm({**signup_data, 'email': invite.email})
            if not form.is_valid():
                raise ValidationError(form.errors.as_data())
            password = form.save(commit=False).password
        # An invitation can provision a new account, but cannot authenticate an
        # account that was created in between the lookup and this write.
        user, created = User.objects.get_or_create(
            email=invite.email.lower(), defaults={'password': password}
        )
        if not created:
            return {'result': 'sign_in_required', 'invite': invite}

    if not user.is_active:
        return {'result': 'sign_in_required', 'invite': invite}
    if TeamMembership.objects.filter(team_id=team_id, user=user).exists():
        invite.revoked_at = timezone.now()
        invite.save(update_fields=['revoked_at'])
        return {'result': 'already_member', 'invite': invite, 'user': user}
    membership = accept_invite(invite=invite, user=user)
    return {'result': 'accepted', 'invite': invite, 'membership': membership, 'user': user}


def received_team_invites(user):
    if not user.is_authenticated:
        return TeamInvite.objects.none()
    notified_ids = list(InAppNotification.objects.filter(
        recipient=user, event_type='team.invite.received',
    ).values_list('metadata__invite_id', flat=True))
    return TeamInvite.objects.filter(pk__in=notified_ids, email__iexact=user.email)


def get_team_or_404_for_user(user, team_id):
    return get_team_membership_or_404(user, team_id).team


def get_team_membership_or_404(user, team_id):
    ensure_team_creator_memberships(user)
    return get_object_or_404(
        TeamMembership.objects.select_related('team'), user=user, team_id=team_id
    )


def ensure_team_creator_memberships(user):
    if not getattr(user, 'is_authenticated', False):
        return

    missing_creator_teams = Team.objects.filter(created_by=user).exclude(
        memberships__user=user
    ).exclude(memberships__role=TeamMembership.ROLE_OWNER)
    to_create = [
        TeamMembership(
            team=team,
            user=user,
            role=TeamMembership.ROLE_OWNER,
            invited_by=user,
        )
        for team in missing_creator_teams
    ]
    if to_create:
        TeamMembership.objects.bulk_create(to_create, ignore_conflicts=True)


def team_accent_color(team_id):
    if not team_id:
        return TEAM_ACCENT_PALETTE[0]
    return TEAM_ACCENT_PALETTE[(int(team_id) - 1) % len(TEAM_ACCENT_PALETTE)]

def teams_overview_data(user):
    ensure_team_creator_memberships(user)
    memberships = (
        TeamMembership.objects.filter(user=user)
        .select_related('team')
        .order_by('team__name', 'team__id')
    )
    team_ids = list(memberships.values_list('team_id', flat=True))
    team_subscriptions = list(
        Subscription.objects.filter(team_id__in=team_ids)
        .select_related('team', 'user', 'card')
        .prefetch_related('price_changes')
        .order_by('team__name', 'service_name')
    )
    team_member_counts = {
        row['team_id']: row['member_count']
        for row in (
            TeamMembership.objects.filter(team_id__in=team_ids)
            .values('team_id')
            .annotate(member_count=Count('id'))
        )
    }
    team_cards = [
        {
            'team': membership.team,
            'role': membership.role,
            'member_count': team_member_counts.get(membership.team_id, 0),
            'accent_color': team_accent_color(membership.team_id),
        }
        for membership in memberships
    ]
    team_color_map = {
        membership.team_id: team_accent_color(membership.team_id) for membership in memberships
    }
    monthly_spend_by_currency = {}
    today = timezone.localdate()
    for sub in team_subscriptions:
        if not sub.bills_on(today):
            continue
        currency = (sub.currency or 'USD').upper()
        amount = monthly_equivalent(sub.price_on(today), sub.billing_cycle)
        monthly_spend_by_currency[currency] = monthly_spend_by_currency.get(currency, Decimal('0')) + amount
    monthly_spend_by_currency = {
        currency: amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        for currency, amount in sorted(monthly_spend_by_currency.items())
    }
    team_subscription_rows = [
        {
            'subscription': sub,
            'accent_color': team_accent_color(sub.team_id),
        }
        for sub in team_subscriptions
    ]

    return {
        'teams': [membership.team for membership in memberships],
        'team_cards': team_cards,
        'team_subscriptions': team_subscriptions,
        'team_subscription_rows': team_subscription_rows,
        'team_color_map': team_color_map,
        'teams_monthly_spend': monthly_spend_by_currency.get('USD', Decimal('0.00')),
        'teams_monthly_spend_by_currency': monthly_spend_by_currency,
    }

def team_detail_data(user, team_id):
    membership = get_team_membership_or_404(user, team_id)
    team = membership.team
    return {
        'team': team,
        'membership': membership,
        'is_team_owner': membership.is_owner,
        'can_add_or_request_subscription': membership.role in (TeamMembership.ROLE_OWNER, TeamMembership.ROLE_MEMBER),
        'team_subscriptions': team.subscriptions.select_related('user', 'card', 'renewal_review__decided_by').prefetch_related(
            'participants', 'price_changes'
        ).order_by('service_name'),
        'team_members': team.memberships.select_related('user').order_by('role', 'user__email'),
        'pending_requests': team.subscription_requests.filter(
            status=TeamSubscriptionRequest.STATUS_PENDING
        ).select_related('requested_by'),
        'team_accent_color': team_accent_color(team_id),
    }

def create_subscription_from_request_payload(team_request, reviewer):
    payload = team_request.payload or {}
    start_date = payload.get('start_date')
    if isinstance(start_date, str):
        try:
            start_date = date.fromisoformat(start_date)
        except ValueError:
            start_date = timezone.localdate()
    elif start_date is None:
        start_date = timezone.localdate()

    renewal_time = payload.get('renewal_time')
    if isinstance(renewal_time, str):
        try:
            renewal_time = time.fromisoformat(renewal_time)
        except ValueError:
            renewal_time = None

    subscription = Subscription.objects.create(
        user=team_request.requested_by,
        team=team_request.team,
        service_name=payload.get('service_name', ''),
        display_color=payload.get('display_color') or '',
        plan_name=payload.get('plan_name') or None,
        category=payload.get('category', ''),
        billing_cycle=payload.get('billing_cycle', 'monthly'),
        cost=payload.get('cost', 0),
        user_cost=payload.get('user_cost', payload.get('cost', 0)),
        is_shared=bool(payload.get('is_shared')),
        split_type=payload.get('split_type', 'equal'),
        currency=payload.get('currency', 'USD'),
        start_date=start_date,
        paid_through=date.fromisoformat(payload['paid_through']) if payload.get('paid_through') else None,
        trial_end_date=date.fromisoformat(payload['trial_end_date']) if payload.get('trial_end_date') else None,
        cancel_by_date=date.fromisoformat(payload['cancel_by_date']) if payload.get('cancel_by_date') else None,
        renewal_time=renewal_time,
        status=payload.get('status', 'active'),
        reminders_enabled=bool(payload.get('reminders_enabled', True)),
        notes=payload.get('notes') or '',
        account_email=payload.get('account_email') or None,
        # Never materialize passwords from request payloads.
        account_password=None,
        card=None,
    )
    for field in ('pause_from', 'resume_on', 'introductory_until', 'access_until'):
        setattr(subscription, field, date.fromisoformat(payload[field]) if payload.get(field) else None)
    for field in ('introductory_cost', 'cancellation_url', 'cancellation_state', 'cancellation_notes'):
        if payload.get(field) is not None:
            setattr(subscription, field, payload[field])
    subscription.save()

    participants = payload.get('participants') or []
    to_create = []
    for participant in participants:
        name = (participant.get('name') or '').strip()
        if not name:
            continue
        to_create.append(
            SubscriptionParticipant(
                subscription=subscription,
                name=name,
                share_amount=participant.get('share_amount') or None,
                member_id=participant.get('member_id') if TeamMembership.objects.filter(team=team_request.team, user_id=participant.get('member_id')).exists() else None,
            )
        )
    if to_create:
        SubscriptionParticipant.objects.bulk_create(to_create)

    offsets = payload.get('reminder_offsets') or []
    for raw_offset in offsets:
        try:
            days = int(raw_offset)
        except (TypeError, ValueError):
            continue
        if 1 <= days <= 30:
            ReminderOffset.objects.get_or_create(subscription=subscription, days_before=days)

    record_due_charge_for_subscription(subscription)
    from finance.permissions import log_activity
    log_activity(reviewer, subscription, 'subscription.request.approved', {'request_id': team_request.pk})

    team_request.status = TeamSubscriptionRequest.STATUS_APPROVED
    team_request.reviewed_by = reviewer
    team_request.reviewed_at = timezone.now()
    team_request.created_subscription = subscription
    team_request.save(
        update_fields=['status', 'reviewed_by', 'reviewed_at', 'created_subscription', 'updated_at']
    )

    return subscription


@transaction.atomic
def create_team(*, name, user):
    team = Team.objects.create(name=name, created_by=user)
    TeamMembership.objects.create(
        team=team, user=user, role=TeamMembership.ROLE_OWNER, invited_by=user
    )
    return team


@transaction.atomic
def remove_team_member(*, team, membership_id, actor):
    Team.objects.select_for_update().get(pk=team.pk)
    if not is_team_owner(actor, team):
        raise TeamActionError('Only team owners can remove members.', status_code=403)

    membership = get_object_or_404(team.memberships.select_related('user'), pk=membership_id)
    if membership.user_id == actor.pk:
        raise TeamActionError('Use leave team to remove yourself.')
    if membership.is_owner:
        raise TeamActionError('Cannot remove another owner from this action.')

    removed_user = membership.user
    membership.delete()
    create_notification(
        recipient=removed_user,
        actor=actor,
        team=team,
        event_type='team.member.removed',
        title=f'Removed from {team.name}',
        body=f'{actor.email} removed you from {team.name}.',
        link_url=reverse('accounts:teams_overview'),
        metadata={'team_id': team.pk, 'action': 'removed'},
        send_email_alert=True,
    )
    return f'{removed_user.email} was removed from the team.'


def leave_team(*, team, user):
    with transaction.atomic():
        Team.objects.select_for_update().get(pk=team.pk)
        membership = user_team_membership(user, team)
        if not membership:
            raise Http404('Team membership not found.')
        owners = team.memberships.filter(role=TeamMembership.ROLE_OWNER)
        if membership.is_owner and owners.count() <= 1:
            raise TeamActionError('You are the last owner and cannot leave this team.')
        membership.delete()

    for owner in owners.select_related('user'):
        create_notification(
            recipient=owner.user,
            actor=user,
            team=team,
            event_type='team.member.left',
            title=f'{user.email} left {team.name}',
            body=f'{user.email} left the team.',
            link_url=reverse('accounts:team_detail', args=[team.pk]),
            metadata={'team_id': team.pk, 'member_email': user.email, 'action': 'left'},
            send_email_alert=True,
        )
    return f'You left {team.name}.'


def delete_team(*, team, actor):
    if not is_team_owner(actor, team):
        raise TeamActionError('Only team owners can delete teams.', status_code=403)
    team_name = team.name
    subscription_count = team.subscriptions.count()
    team.delete()
    return f'Team "{team_name}" deleted. Removed {subscription_count} team subscription(s).'


@transaction.atomic
def delete_user_account(user):
    member_team_ids = TeamMembership.objects.filter(user=user).values('team_id')
    subscription_team_ids = Subscription.objects.filter(user=user, team__isnull=False).values('team_id')
    charge_team_ids = Transaction.objects.filter(user=user, team__isnull=False).values('team_id')
    teams = Team.objects.select_for_update().filter(
        Q(created_by=user) | Q(pk__in=member_team_ids) | Q(pk__in=subscription_team_ids) | Q(pk__in=charge_team_ids),
    ).order_by('pk')
    empty_team_ids = []
    for team in teams:
        remaining = team.memberships.exclude(user=user)
        next_owner_id = remaining.filter(role=TeamMembership.ROLE_OWNER).order_by('pk').values_list(
            'user_id', flat=True,
        ).first()
        if next_owner_id is not None:
            Subscription.objects.filter(team=team, user=user).update(user_id=next_owner_id)
            Transaction.objects.filter(team=team, user=user).update(user_id=next_owner_id)
            continue
        if remaining.exists():
            raise TeamActionError(
                f'Add another owner to {team.name} or delete the team before deleting your account.',
                status_code=409,
            )
        empty_team_ids.append(team.pk)

    Team.objects.filter(pk__in=empty_team_ids).delete()
    user.delete()


@transaction.atomic
def rotate_team_invite(*, team, email, role, actor):
    Team.objects.select_for_update().get(pk=team.pk)
    if not is_team_owner(actor, team):
        raise TeamActionError('Only team owners can invite members.', status_code=403)
    if TeamMembership.objects.filter(team=team, user__email__iexact=email).exists():
        raise TeamActionError('That email is already a team member.')
    now = timezone.now()
    previous = team.invites.filter(
        email__iexact=email,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
    )
    replaced = previous.filter(expires_at__gt=now).exists()
    previous.update(revoked_at=now)
    invite, raw_token = create_team_invite(team=team, email=email, role=role, invited_by=actor)
    return invite, raw_token, bool(replaced)


@transaction.atomic
def revoke_team_invite(*, team, invite_id, actor):
    Team.objects.select_for_update().get(pk=team.pk)
    if not is_team_owner(actor, team):
        raise TeamActionError('Only team owners can revoke invitations.', status_code=403)
    invite = get_object_or_404(TeamInvite.objects.select_for_update(), team=team, pk=invite_id)
    if invite.accepted_at:
        raise TeamActionError('This invitation has already been accepted.', status_code=409)
    if not invite.revoked_at:
        invite.revoked_at = timezone.now()
        invite.save(update_fields=['revoked_at'])
    return 'Invitation revoked.'


def invite_team_member(*, team, email, role, actor, send_invite):
    if not is_team_owner(actor, team):
        raise TeamActionError('Only team owners can invite members.', status_code=403)

    invite, raw_token, replaced = rotate_team_invite(team=team, email=email, role=role, actor=actor)

    email_sent = True
    try:
        send_invite(invite, raw_token)
    except Exception:
        email_sent = False
        logger.exception('Failed to send team invite email for team=%s email=%s', team.pk, email)

    invitee = User.objects.filter(email__iexact=email).first()
    if invitee and invitee.pk != actor.pk:
        create_notification(
            recipient=invitee,
            actor=actor,
            team=team,
            event_type='team.invite.received',
            title=f'Invitation to join {team.name}',
            body=f'{actor.email} invited you as {role}. Open this invitation to join.',
            link_url=reverse('accounts:teams_overview'),
            metadata={'invite_id': invite.pk, 'team_id': team.pk, 'role': role},
            send_email_alert=False,
        )

    create_team_notifications(
        team=team,
        actor=actor,
        event_type='team.invite.sent',
        title=f'Invitation sent to {email}',
        body=f'{actor.email} invited {email} to {team.name}.',
        link_url=reverse('accounts:team_detail', args=[team.pk]),
        metadata={'invite_id': invite.pk, 'email': email, 'role': role},
        send_email_alert=True,
    )

    if not email_sent:
        message = f'Invite created for {email}, but email delivery failed. Check SMTP settings and retry.'
    elif replaced:
        message = f'Invitation re-sent to {email}.'
    else:
        message = f'Invitation sent to {email}.'
    return {'email_sent': email_sent, 'message': message, 'invite_url': invite_accept_url(raw_token)}


def notify_invite_accepted(*, invite, membership, user):
    create_team_notifications(
        team=invite.team,
        actor=user,
        event_type='team.invite.accepted',
        title=f'{user.email} joined {invite.team.name}',
        body=f'{user.email} accepted an invitation as {membership.role}.',
        link_url=reverse('accounts:team_detail', args=[invite.team_id]),
        metadata={'membership_role': membership.role},
        send_email_alert=True,
    )


def reveal_team_subscription_password(*, team, subscription_id):
    subscription = get_object_or_404(team.subscriptions, pk=subscription_id)
    if not subscription.account_password:
        raise TeamActionError('No password set.', status_code=404)
    password = subscription.get_account_password()
    if not password:
        raise TeamActionError('Password unavailable.', status_code=404)
    return password


def review_team_request(*, request_id, reviewer, approve, decision_note=''):
    with transaction.atomic():
        team_id = get_object_or_404(TeamSubscriptionRequest, pk=request_id).team_id
        Team.objects.select_for_update().get(pk=team_id)
        team_request = get_object_or_404(
            TeamSubscriptionRequest.objects.select_for_update().select_related('team', 'requested_by'),
            pk=request_id,
        )
        if not is_team_owner(reviewer, team_request.team):
            action = 'approve' if approve else 'reject'
            raise TeamActionError(f'Only team owners can {action} requests.', status_code=403)
        if team_request.status != TeamSubscriptionRequest.STATUS_PENDING:
            raise TeamActionError('This request has already been processed.', status_code=409)

        if approve:
            if not TeamMembership.objects.filter(
                team=team_request.team, user=team_request.requested_by,
                role__in=(TeamMembership.ROLE_OWNER, TeamMembership.ROLE_MEMBER),
            ).exists():
                raise TeamActionError('The requester is no longer allowed to add team subscriptions.', status_code=409)
            subscription = create_subscription_from_request_payload(team_request, reviewer)
            event_type = 'team.request.approved'
            title = f'Request approved: {subscription.service_name}'
            metadata = {'request_id': team_request.pk, 'subscription_id': subscription.pk}
        else:
            team_request.status = TeamSubscriptionRequest.STATUS_REJECTED
            team_request.reviewed_by = reviewer
            team_request.reviewed_at = timezone.now()
            team_request.decision_note = decision_note.strip()
            team_request.save(
                update_fields=['status', 'reviewed_by', 'reviewed_at', 'decision_note', 'updated_at']
            )
            subscription = None
            event_type = 'team.request.rejected'
            title = 'Subscription request rejected'
            metadata = {'request_id': team_request.pk}

    action = 'approved' if approve else 'rejected'
    create_team_notifications(
        team=team_request.team,
        actor=reviewer,
        subscription=subscription,
        event_type=event_type,
        title=title,
        body=f'{reviewer.email} {action} a subscription request.',
        link_url=reverse('accounts:team_detail', args=[team_request.team_id]),
        metadata=metadata,
        send_email_alert=True,
    )
    return team_request
