from datetime import date, time
import logging

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
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
from .models import Team, TeamMembership
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
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'profile':
            profile_form = ProfileSettingsForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                return redirect(f"{reverse('accounts:settings')}?updated=profile")

        if form_type == 'password':
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
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
        },
    )


def _get_team_or_404_for_user(user, team_id):
    team = get_object_or_404(Team, pk=team_id)
    if not is_team_member(user, team):
        raise Http404("Team not found.")
    return team


@login_required
def teams_overview(request):
    memberships = TeamMembership.objects.filter(user=request.user).select_related('team')
    team_ids = memberships.values_list('team_id', flat=True)
    team_subscriptions = (
        Subscription.objects.filter(team_id__in=team_ids)
        .select_related('team', 'user', 'card')
        .order_by('team__name', 'service_name')
    )
    teams = [membership.team for membership in memberships]
    return render(
        request,
        'accounts/teams_overview.html',
        {
            'teams': teams,
            'team_subscriptions': team_subscriptions,
        },
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
    else:
        form = TeamCreateForm()

    return render(request, 'accounts/team_create.html', {'form': form})


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
    if existing_invite:
        messages.error(request, 'An active invite for that email already exists.')
        return redirect('accounts:team_detail', team_id=team.pk)

    try:
        with transaction.atomic():
            invite, raw_token = create_team_invite(
                team=team,
                email=email,
                role=role,
                invited_by=request.user,
            )
            # Keep DB and delivery state aligned: if email fails, rollback invite row.
            send_team_invite_email(invite, raw_token)
    except Exception:
        logger.exception("Failed to create/send team invite for team=%s email=%s", team.pk, email)
        messages.error(request, 'Invitation could not be sent. Please try again.')
        return redirect('accounts:team_detail', team_id=team.pk)

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

    messages.success(request, f'Invitation sent to {email}.')
    return redirect('accounts:team_detail', team_id=team.pk)


def invite_accept(request, token):
    invite = resolve_invite(token)
    if not invite:
        messages.error(request, 'This invitation link is invalid.')
        return render(request, 'accounts/invite_accept.html', {'invite': None, 'invite_status': 'invalid'})

    if not request.user.is_authenticated:
        return redirect(f"{reverse('accounts:login')}?next={request.path}")

    if request.user.email.lower() != invite.email.lower():
        messages.error(
            request,
            f"This invite is for {invite.email}. You are logged in as {request.user.email}.",
        )
        return render(
            request,
            'accounts/invite_accept.html',
            {'invite': invite, 'invite_status': 'email_mismatch'},
        )

    if TeamMembership.objects.filter(team=invite.team, user=request.user).exists():
        if invite.accepted_at is None and invite.revoked_at is None:
            invite.revoked_at = timezone.now()
            invite.save(update_fields=['revoked_at'])
        messages.info(request, f"You are already a member of {invite.team.name}.")
        return redirect('accounts:team_detail', team_id=invite.team.pk)

    if not invite.is_usable():
        if invite.accepted_at:
            status = 'already_used'
        elif invite.revoked_at:
            status = 'revoked'
        else:
            status = 'expired'
        return render(
            request,
            'accounts/invite_accept.html',
            {'invite': invite, 'invite_status': status},
        )

    if request.method == 'POST':
        membership = accept_invite(invite=invite, user=request.user)
        create_team_notifications(
            team=invite.team,
            actor=request.user,
            event_type='team.invite.accepted',
            title=f"{request.user.email} joined {invite.team.name}",
            body=f"{request.user.email} accepted an invitation as {membership.role}.",
            link_url=reverse('accounts:team_detail', args=[invite.team.pk]),
            metadata={'membership_role': membership.role},
            send_email_alert=True,
        )
        messages.success(request, f"You joined {invite.team.name}.")
        return redirect('accounts:team_detail', team_id=invite.team.pk)

    return render(
        request,
        'accounts/invite_accept.html',
        {'invite': invite, 'invite_status': 'ready'},
    )


@login_required
def team_subscription_password(request, team_id, subscription_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'POST required.'}, status=405)

    team = _get_team_or_404_for_user(request.user, team_id)
    if not is_team_owner(request.user, team):
        return JsonResponse({'ok': False, 'message': 'Only team owners can view credentials.'}, status=403)

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
