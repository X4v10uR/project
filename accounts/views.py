from datetime import date, time
from decimal import Decimal, ROUND_HALF_UP
import logging

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.db import transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone

from subscriptions.models import ReminderOffset, Subscription, SubscriptionParticipant, TeamSubscriptionRequest
from subscriptions.notifications import create_notification, create_team_notifications

from .forms import (
    CustomUserCreationForm,
    ProfileSettingsForm,
    TeamCreateForm,
    TeamInviteForm,
)
from .models import Team, TeamInvite, TeamMembership, User
from .services import (
    accept_invite,
    create_team_invite,
    is_team_member,
    is_team_owner,
    resolve_invite,
    send_team_invite_email,
    user_team_membership,
)

logger = logging.getLogger(__name__)

TEAM_ACCENT_PALETTE = (
    "#E8F542",
    "#7ECDC4",
    "#C5B8F5",
    "#F7D9A0",
    "#A9D8F7",
    "#F5B8D8",
)


def signup(request):
    raw_next = request.POST.get('next') or request.GET.get('next') or ''
    safe_next = ''
    if raw_next and url_has_allowed_host_and_scheme(raw_next, allowed_hosts={request.get_host()}):
        safe_next = raw_next

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if safe_next:
                return redirect(safe_next)
            return redirect('dashboard:home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form, 'next': safe_next})


@login_required
def settings(request):
    profile_form = ProfileSettingsForm(instance=request.user)
    password_form_class = PasswordChangeForm if request.user.has_usable_password() else SetPasswordForm
    password_form = password_form_class(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'profile':
            profile_form = ProfileSettingsForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                return redirect(f"{reverse('accounts:settings')}?updated=profile")

        if form_type == 'password':
            password_form = password_form_class(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                return redirect(f"{reverse('accounts:settings')}?updated=password")

    updated = request.GET.get('updated', '')
    return render(
        request,
        'accounts/settings.html',
        {
            'profile_form': profile_form,
            'password_form': password_form,
            'profile_updated': updated == 'profile',
            'password_updated': updated == 'password',
            'password_mode': 'change' if request.user.has_usable_password() else 'set',
        },
    )


def _invite_status(invite):
    if invite.accepted_at:
        return 'already_used'
    if invite.revoked_at:
        return 'revoked'
    if invite.is_expired():
        return 'expired'
    return 'ready'


def _accept_invite_with_lock(*, invite_id, user):
    with transaction.atomic():
        locked_invite = (
            TeamInvite.objects
            .select_for_update()
            .select_related('team', 'invited_by')
            .filter(pk=invite_id)
            .first()
        )
        if not locked_invite:
            return {'result': 'invalid', 'invite': None}

        if TeamMembership.objects.filter(team=locked_invite.team, user=user).exists():
            if (
                locked_invite.accepted_at is None
                and locked_invite.revoked_at is None
                and not locked_invite.is_expired()
            ):
                locked_invite.revoked_at = timezone.now()
                locked_invite.save(update_fields=['revoked_at'])
            return {'result': 'already_member', 'invite': locked_invite}

        invite_status = _invite_status(locked_invite)
        if invite_status != 'ready':
            return {'result': invite_status, 'invite': locked_invite}

        membership = accept_invite(invite=locked_invite, user=user)
        return {'result': 'accepted', 'invite': locked_invite, 'membership': membership}


def _get_team_or_404_for_user(user, team_id):
    _ensure_creator_memberships(user)
    team = get_object_or_404(Team, pk=team_id)
    if not is_team_member(user, team):
        raise Http404("Team not found.")
    return team


def _ensure_creator_memberships(user):
    if not getattr(user, 'is_authenticated', False):
        return

    missing_creator_teams = Team.objects.filter(created_by=user).exclude(
        memberships__user=user
    )
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


def _team_accent_color(team_id):
    if not team_id:
        return TEAM_ACCENT_PALETTE[0]
    return TEAM_ACCENT_PALETTE[(int(team_id) - 1) % len(TEAM_ACCENT_PALETTE)]


def _monthly_equivalent(cost, billing_cycle):
    amount = Decimal(cost or 0)
    if billing_cycle == 'weekly':
        return amount * Decimal('52') / Decimal('12')
    if billing_cycle == 'yearly':
        return amount / Decimal('12')
    return amount


def _build_teams_overview_context(request, *, form=None, teams_ui_mode='overview'):
    _ensure_creator_memberships(request.user)
    memberships = (
        TeamMembership.objects.filter(user=request.user)
        .select_related('team')
        .order_by('team__name', 'team__id')
    )
    team_ids = list(memberships.values_list('team_id', flat=True))
    team_subscriptions = list(
        Subscription.objects.filter(team_id__in=team_ids)
        .select_related('team', 'user', 'card')
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
            'accent_color': _team_accent_color(membership.team_id),
        }
        for membership in memberships
    ]
    team_color_map = {
        membership.team_id: _team_accent_color(membership.team_id) for membership in memberships
    }
    monthly_total = sum(
        (_monthly_equivalent(sub.cost, sub.billing_cycle) for sub in team_subscriptions),
        Decimal('0'),
    ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    team_subscription_rows = [
        {
            'subscription': sub,
            'accent_color': _team_accent_color(sub.team_id),
        }
        for sub in team_subscriptions
    ]

    return {
        'teams': [membership.team for membership in memberships],
        'team_cards': team_cards,
        'team_subscriptions': team_subscriptions,
        'team_subscription_rows': team_subscription_rows,
        'team_color_map': team_color_map,
        'teams_monthly_spend': monthly_total,
        'teams_ui_mode': teams_ui_mode,
        'team_create_form': form or TeamCreateForm(),
        'hide_sidebar': True,
        'hide_global_notifications': True,
        'suppress_base_messages': True,
    }


@login_required
def teams_overview(request):
    return render(
        request,
        'accounts/teams_overview.html',
        _build_teams_overview_context(request, teams_ui_mode='overview'),
    )


@login_required
def team_detail(request, team_id):
    team = _get_team_or_404_for_user(request.user, team_id)
    membership = user_team_membership(request.user, team)
    is_owner = bool(membership and membership.is_owner)

    subscriptions = (
        team.subscriptions.select_related('user', 'card')
        .prefetch_related('participants')
        .order_by('service_name')
    )
    members = team.memberships.select_related('user').order_by('role', 'user__email')
    pending_requests = team.subscription_requests.filter(
        status=TeamSubscriptionRequest.STATUS_PENDING
    ).select_related('requested_by')
    invite_form = TeamInviteForm()

    return render(
        request,
        'accounts/team_detail.html',
        {
            'team': team,
            'membership': membership,
            'is_team_owner': is_owner,
            'team_subscriptions': subscriptions,
            'team_members': members,
            'pending_requests': pending_requests,
            'invite_form': invite_form,
            'team_accent_color': _team_accent_color(team.id),
            'hide_sidebar': True,
            'hide_global_notifications': True,
            'suppress_base_messages': True,
        },
    )


@login_required
def team_create(request):
    if request.method == 'POST':
        form = TeamCreateForm(request.POST)
        if form.is_valid():
            team = form.save(commit=False)
            team.created_by = request.user
            team.save()
            TeamMembership.objects.create(
                team=team,
                user=request.user,
                role=TeamMembership.ROLE_OWNER,
                invited_by=request.user,
            )
            messages.success(request, 'Team created successfully.')
            return redirect('accounts:team_detail', team_id=team.pk)
        return render(
            request,
            'accounts/teams_overview.html',
            _build_teams_overview_context(
                request,
                form=form,
                teams_ui_mode='create',
            ),
        )
    else:
        form = TeamCreateForm()

    return render(
        request,
        'accounts/teams_overview.html',
        _build_teams_overview_context(
            request,
            form=form,
            teams_ui_mode='create',
        ),
    )


@login_required
def team_member_remove(request, team_id, membership_id):
    if request.method != 'POST':
        return redirect('accounts:team_detail', team_id=team_id)

    team = _get_team_or_404_for_user(request.user, team_id)
    if not is_team_owner(request.user, team):
        messages.error(request, 'Only team owners can remove members.')
        return redirect('accounts:team_detail', team_id=team.pk)

    target_membership = get_object_or_404(
        team.memberships.select_related('user'),
        pk=membership_id,
    )

    if target_membership.user_id == request.user.id:
        messages.error(request, 'Use leave team to remove yourself.')
        return redirect('accounts:team_detail', team_id=team.pk)

    if target_membership.role == TeamMembership.ROLE_OWNER:
        messages.error(request, 'Cannot remove another owner from this action.')
        return redirect('accounts:team_detail', team_id=team.pk)

    removed_user = target_membership.user
    removed_email = removed_user.email
    target_membership.delete()

    create_notification(
        recipient=removed_user,
        actor=request.user,
        team=team,
        event_type='team.member.removed',
        title=f"Removed from {team.name}",
        body=f"{request.user.email} removed you from {team.name}.",
        link_url=reverse('accounts:teams_overview'),
        metadata={'team_id': team.pk, 'action': 'removed'},
        send_email_alert=True,
    )

    messages.success(request, f'{removed_email} was removed from the team.')
    return redirect('accounts:team_detail', team_id=team.pk)


@login_required
def team_leave(request, team_id):
    if request.method != 'POST':
        return redirect('accounts:team_detail', team_id=team_id)

    team = _get_team_or_404_for_user(request.user, team_id)
    membership = user_team_membership(request.user, team)
    if not membership:
        raise Http404("Team membership not found.")

    if membership.role == TeamMembership.ROLE_OWNER:
        owner_count = team.memberships.filter(role=TeamMembership.ROLE_OWNER).count()
        if owner_count <= 1:
            messages.error(request, 'You are the last owner and cannot leave this team.')
            return redirect('accounts:team_detail', team_id=team.pk)

    leaver = request.user
    leaver_email = leaver.email
    membership.delete()

    owner_memberships = (
        team.memberships
        .select_related('user')
        .filter(role=TeamMembership.ROLE_OWNER)
    )
    for owner_membership in owner_memberships:
        create_notification(
            recipient=owner_membership.user,
            actor=leaver,
            team=team,
            event_type='team.member.left',
            title=f"{leaver_email} left {team.name}",
            body=f"{leaver_email} left the team.",
            link_url=reverse('accounts:team_detail', args=[team.pk]),
            metadata={'team_id': team.pk, 'member_email': leaver_email, 'action': 'left'},
            send_email_alert=True,
        )

    messages.success(request, f'You left {team.name}.')
    return redirect('accounts:teams_overview')


@login_required
def team_delete(request, team_id):
    team = _get_team_or_404_for_user(request.user, team_id)
    if not is_team_owner(request.user, team):
        messages.error(request, 'Only team owners can delete teams.')
        return redirect('accounts:team_detail', team_id=team.pk)

    if request.method != 'POST':
        return redirect('accounts:team_detail', team_id=team.pk)

    team_name = team.name
    subscription_count = team.subscriptions.count()
    team.delete()

    messages.success(
        request,
        f'Team "{team_name}" deleted. Removed {subscription_count} team subscription(s).',
    )
    return redirect('accounts:teams_overview')


@login_required
def team_invite(request, team_id):
    if request.method != 'POST':
        return redirect('accounts:team_detail', team_id=team_id)

    team = _get_team_or_404_for_user(request.user, team_id)
    if not is_team_owner(request.user, team):
        messages.error(request, 'Only team owners can invite members.')
        return redirect('accounts:team_detail', team_id=team.pk)

    form = TeamInviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a valid invite email and role.')
        return redirect('accounts:team_detail', team_id=team.pk)

    email = form.cleaned_data['email']
    role = form.cleaned_data['role']

    if TeamMembership.objects.filter(team=team, user__email__iexact=email).exists():
        messages.error(request, 'That email is already a team member.')
        return redirect('accounts:team_detail', team_id=team.pk)

    existing_invite = team.invites.filter(
        email__iexact=email,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    replaced_existing = False
    if existing_invite:
        # Rotate active invites so owners can re-send and generate a fresh token.
        existing_invite.revoked_at = timezone.now()
        existing_invite.save(update_fields=['revoked_at'])
        replaced_existing = True

    try:
        invite, raw_token = create_team_invite(
            team=team,
            email=email,
            role=role,
            invited_by=request.user,
        )
    except Exception:
        logger.exception("Failed to create/send team invite for team=%s email=%s", team.pk, email)
        messages.error(request, 'Invitation could not be created. Please try again.')
        return redirect('accounts:team_detail', team_id=team.pk)

    email_sent = True
    try:
        send_team_invite_email(invite, raw_token)
    except Exception:
        email_sent = False
        logger.exception("Failed to send team invite email for team=%s email=%s", team.pk, email)

    invitee_user = User.objects.filter(email__iexact=email).first()
    if invitee_user and invitee_user.pk != request.user.pk:
        create_notification(
            recipient=invitee_user,
            actor=request.user,
            team=team,
            event_type='team.invite.received',
            title=f"Invitation to join {team.name}",
            body=f"{request.user.email} invited you as {role}.",
            link_url=reverse('accounts:invite_accept', args=[raw_token]),
            metadata={'invite_id': invite.pk, 'team_id': team.pk, 'role': role},
            send_email_alert=False,
        )

    if not email_sent and invitee_user:
        messages.warning(
            request,
            f'Invite created for {email}, but email delivery failed. The user can accept from in-app notifications.',
        )
    elif not email_sent:
        messages.warning(
            request,
            f'Invite created for {email}, but email delivery failed. Check SMTP settings and retry.',
        )
    elif replaced_existing:
        messages.success(request, f'Invitation re-sent to {email}.')
    else:
        messages.success(request, f'Invitation sent to {email}.')

    create_team_notifications(
        team=team,
        actor=request.user,
        event_type='team.invite.sent',
        title=f"Invitation sent to {email}",
        body=f"{request.user.email} invited {email} to {team.name}.",
        link_url=reverse('accounts:team_detail', args=[team.pk]),
        metadata={'invite_id': invite.pk, 'email': email, 'role': role},
        send_email_alert=True,
    )
    return redirect('accounts:team_detail', team_id=team.pk)


def invite_accept(request, token):
    invite = resolve_invite(token)
    if not invite:
        messages.error(request, 'This invitation link is invalid.')
        return render(request, 'accounts/invite_accept.html', {'invite': None, 'invite_status': 'invalid'})

    auto_provisioned = False
    current_user = request.user if request.user.is_authenticated else None

    if current_user and current_user.email.lower() != invite.email.lower():
        if request.method != 'POST' or request.POST.get('action') != 'switch_account':
            return render(
                request,
                'accounts/invite_accept.html',
                {
                    'invite': invite,
                    'invite_status': 'email_mismatch',
                    'current_email': current_user.email,
                },
            )
        logout(request)
        current_user = None

    if current_user is None:
        initial_status = _invite_status(invite)
        if initial_status != 'ready':
            return render(
                request,
                'accounts/invite_accept.html',
                {'invite': invite, 'invite_status': initial_status},
            )

        invited_user = User.objects.filter(email__iexact=invite.email).first()
        if not invited_user:
            invited_user = User.objects.create_user(email=invite.email)
            auto_provisioned = True

        login(request, invited_user, backend='django.contrib.auth.backends.ModelBackend')
        current_user = invited_user

    accept_result = _accept_invite_with_lock(invite_id=invite.pk, user=current_user)
    result_type = accept_result['result']
    locked_invite = accept_result.get('invite') or invite

    if result_type == 'accepted':
        membership = accept_result['membership']
        create_team_notifications(
            team=locked_invite.team,
            actor=current_user,
            event_type='team.invite.accepted',
            title=f"{current_user.email} joined {locked_invite.team.name}",
            body=f"{current_user.email} accepted an invitation as {membership.role}.",
            link_url=reverse('accounts:team_detail', args=[locked_invite.team.pk]),
            metadata={'membership_role': membership.role},
            send_email_alert=True,
        )
        messages.success(request, f"You joined {locked_invite.team.name}.")
        if auto_provisioned or not current_user.has_usable_password():
            messages.info(
                request,
                'You signed in with a secure invite link. You can set a password later in Settings.',
            )
        return redirect('accounts:team_detail', team_id=locked_invite.team.pk)

    if result_type == 'already_member':
        messages.info(request, f"You are already a member of {locked_invite.team.name}.")
        return redirect('accounts:team_detail', team_id=locked_invite.team.pk)

    if result_type in {'already_used', 'revoked', 'expired'}:
        return render(
            request,
            'accounts/invite_accept.html',
            {'invite': locked_invite, 'invite_status': result_type},
        )

    messages.error(request, 'This invitation link is invalid.')
    return render(
        request,
        'accounts/invite_accept.html',
        {'invite': None, 'invite_status': 'invalid'},
    )


@login_required
def team_subscription_password(request, team_id, subscription_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'POST required.'}, status=405)

    team = _get_team_or_404_for_user(request.user, team_id)

    subscription = get_object_or_404(
        Subscription.objects.select_related('team'),
        pk=subscription_id,
        team=team,
    )
    if not subscription.account_password:
        return JsonResponse({'ok': False, 'message': 'No password set.'}, status=404)

    raw_password = subscription.get_account_password()
    if not raw_password:
        return JsonResponse({'ok': False, 'message': 'Password unavailable.'}, status=404)

    return JsonResponse({'ok': True, 'password': raw_password})


def _create_subscription_from_request_payload(team_request, reviewer):
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
        plan_name=payload.get('plan_name') or None,
        category=payload.get('category', ''),
        billing_cycle=payload.get('billing_cycle', 'monthly'),
        cost=payload.get('cost', 0),
        user_cost=payload.get('user_cost', payload.get('cost', 0)),
        is_shared=bool(payload.get('is_shared')),
        split_type=payload.get('split_type', 'equal'),
        currency=payload.get('currency', 'USD'),
        start_date=start_date,
        renewal_time=renewal_time,
        status=payload.get('status', 'active'),
        reminders_enabled=bool(payload.get('reminders_enabled', True)),
        notes=payload.get('notes') or '',
        account_email=payload.get('account_email') or None,
        account_password=payload.get('account_password') or None,
        card=None,
    )

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

    team_request.status = TeamSubscriptionRequest.STATUS_APPROVED
    team_request.reviewed_by = reviewer
    team_request.reviewed_at = timezone.now()
    team_request.created_subscription = subscription
    team_request.save(
        update_fields=['status', 'reviewed_by', 'reviewed_at', 'created_subscription', 'updated_at']
    )

    return subscription


@login_required
def team_request_approve(request, request_id):
    if request.method != 'POST':
        return redirect('accounts:teams_overview')

    with transaction.atomic():
        team_request = get_object_or_404(
            TeamSubscriptionRequest.objects.select_for_update().select_related('team', 'requested_by'),
            pk=request_id,
        )
        if not is_team_owner(request.user, team_request.team):
            messages.error(request, 'Only team owners can approve requests.')
            return redirect('accounts:teams_overview')

        if team_request.status != TeamSubscriptionRequest.STATUS_PENDING:
            messages.error(request, 'This request has already been processed.')
            return redirect('accounts:team_detail', team_id=team_request.team_id)

        subscription = _create_subscription_from_request_payload(team_request, request.user)

    create_team_notifications(
        team=team_request.team,
        actor=request.user,
        subscription=subscription,
        event_type='team.request.approved',
        title=f"Request approved: {subscription.service_name}",
        body=f"{request.user.email} approved a subscription request.",
        link_url=reverse('accounts:team_detail', args=[team_request.team_id]),
        metadata={'request_id': team_request.pk, 'subscription_id': subscription.pk},
        send_email_alert=True,
    )
    messages.success(request, 'Request approved and subscription created.')
    return redirect('accounts:team_detail', team_id=team_request.team_id)


@login_required
def team_request_reject(request, request_id):
    if request.method != 'POST':
        return redirect('accounts:teams_overview')

    with transaction.atomic():
        team_request = get_object_or_404(
            TeamSubscriptionRequest.objects.select_for_update().select_related('team', 'requested_by'),
            pk=request_id,
        )
        if not is_team_owner(request.user, team_request.team):
            messages.error(request, 'Only team owners can reject requests.')
            return redirect('accounts:teams_overview')

        if team_request.status != TeamSubscriptionRequest.STATUS_PENDING:
            messages.error(request, 'This request has already been processed.')
            return redirect('accounts:team_detail', team_id=team_request.team_id)

        note = (request.POST.get('decision_note') or '').strip()
        team_request.status = TeamSubscriptionRequest.STATUS_REJECTED
        team_request.reviewed_by = request.user
        team_request.reviewed_at = timezone.now()
        team_request.decision_note = note
        team_request.save(
            update_fields=['status', 'reviewed_by', 'reviewed_at', 'decision_note', 'updated_at']
        )

    create_team_notifications(
        team=team_request.team,
        actor=request.user,
        event_type='team.request.rejected',
        title="Subscription request rejected",
        body=f"{request.user.email} rejected a subscription request.",
        link_url=reverse('accounts:team_detail', args=[team_request.team_id]),
        metadata={'request_id': team_request.pk},
        send_email_alert=True,
    )
    messages.success(request, 'Request rejected.')
    return redirect('accounts:team_detail', team_id=team_request.team_id)
