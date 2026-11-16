import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import team_workflows as flows
from .forms import CustomUserCreationForm, TeamCreateForm, TeamInviteForm
from subscriptions.models import TeamSubscriptionRequest

from .services import resolve_invite, send_team_invite_email

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

def _build_teams_overview_context(request, *, form=None, teams_ui_mode='overview'):
    return {
        **flows.teams_overview_data(request.user),
        'teams_ui_mode': teams_ui_mode,
        'team_create_form': form or TeamCreateForm(),
        'hide_sidebar': True,
        'hide_global_notifications': True,
        'suppress_base_messages': True,
    }


@login_required
def teams_overview(request):
    return render(
        request, 'accounts/teams_overview.html', _build_teams_overview_context(request)
    )


@login_required
def team_detail(request, team_id):
    return render(
        request,
        'accounts/team_detail.html',
        {
            **flows.team_detail_data(request.user, team_id),
            'invite_form': TeamInviteForm(),
            'hide_sidebar': True,
            'hide_global_notifications': True,
            'suppress_base_messages': True,
        },
    )


@login_required
def team_create(request):
    form = TeamCreateForm(request.POST if request.method == 'POST' else None)
    if form.is_valid():
        team = flows.create_team(name=form.cleaned_data['name'], user=request.user)
        messages.success(request, 'Team created successfully.')
        return redirect('accounts:team_detail', team_id=team.pk)
    return render(
        request,
        'accounts/teams_overview.html',
        _build_teams_overview_context(request, form=form, teams_ui_mode='create'),
    )


@login_required
def team_member_remove(request, team_id, membership_id):
    if request.method == 'POST':
        team = flows.get_team_or_404_for_user(request.user, team_id)
        try:
            message = flows.remove_team_member(
                team=team, membership_id=membership_id, actor=request.user
            )
        except flows.TeamActionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, message)
    return redirect('accounts:team_detail', team_id=team_id)


@login_required
def team_leave(request, team_id):
    if request.method == 'POST':
        team = flows.get_team_or_404_for_user(request.user, team_id)
        try:
            message = flows.leave_team(team=team, user=request.user)
        except flows.TeamActionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, message)
            return redirect('accounts:teams_overview')
    return redirect('accounts:team_detail', team_id=team_id)


@login_required
def team_delete(request, team_id):
    team = flows.get_team_or_404_for_user(request.user, team_id)
    if request.method == 'POST':
        try:
            message = flows.delete_team(team=team, actor=request.user)
        except flows.TeamActionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, message)
            return redirect('accounts:teams_overview')
    return redirect('accounts:team_detail', team_id=team_id)


@login_required
def team_invite(request, team_id):
    if request.method != 'POST':
        return redirect('accounts:team_detail', team_id=team_id)
    team = flows.get_team_or_404_for_user(request.user, team_id)
    form = TeamInviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please provide a valid invite email and role.')
        return redirect('accounts:team_detail', team_id=team_id)
    try:
        result = flows.invite_team_member(
            team=team, actor=request.user, send_invite=send_team_invite_email, **form.cleaned_data
        )
    except flows.TeamActionError as error:
        messages.error(request, str(error))
    except DatabaseError:
        logger.exception('Failed to create team invite for team=%s', team_id)
        messages.error(request, 'Invitation could not be created. Please try again.')
    else:
        notify = messages.success if result['email_sent'] else messages.warning
        notify(request, result['message'])
    return redirect('accounts:team_detail', team_id=team_id)

@require_http_methods(['GET', 'POST'])
@never_cache
def invite_accept(request, token):
    if request.method == 'POST':
        result = flows.redeem_invite(token=token, user=request.user)
        invite, status = result['invite'], result['result']
        if status in {'accepted', 'already_member'}:
            user = result['user']
            if not request.user.is_authenticated:
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            if status == 'accepted':
                flows.notify_invite_accepted(invite=invite, membership=result['membership'], user=user)
                messages.success(request, f'You joined {invite.team.name}.')
            else:
                messages.info(request, f'You are already a member of {invite.team.name}.')
            return redirect('accounts:team_detail', team_id=invite.team_id)
    else:
        invite = resolve_invite(token)
        status = flows.invite_access_status(invite, request.user)

    return render(request, 'accounts/invite_accept.html', {'invite': invite, 'invite_status': status})

@login_required
@never_cache
def team_subscription_password(request, team_id, subscription_id):
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'message': 'POST required.'}, status=405)
    team = flows.get_team_or_404_for_user(request.user, team_id)
    try:
        password = flows.reveal_team_subscription_password(team=team, subscription_id=subscription_id)
    except flows.TeamActionError as error:
        return JsonResponse({'ok': False, 'message': str(error)}, status=error.status_code)
    return JsonResponse({'ok': True, 'password': password})


def _team_request_review(request, request_id, *, approve):
    if request.method != 'POST':
        return redirect('accounts:teams_overview')
    try:
        team_request = flows.review_team_request(
            request_id=request_id,
            reviewer=request.user,
            approve=approve,
            decision_note=request.POST.get('decision_note') or '',
        )
    except flows.TeamActionError as error:
        messages.error(request, str(error))
        if error.status_code == 409:
            team_id = TeamSubscriptionRequest.objects.values_list('team_id', flat=True).get(pk=request_id)
            return redirect('accounts:team_detail', team_id=team_id)
        return redirect('accounts:teams_overview')
    message = 'Request approved and subscription created.' if approve else 'Request rejected.'
    messages.success(request, message)
    return redirect('accounts:team_detail', team_id=team_request.team_id)


@login_required
def team_request_approve(request, request_id):
    return _team_request_review(request, request_id, approve=True)


@login_required
def team_request_reject(request, request_id):
    return _team_request_review(request, request_id, approve=False)
