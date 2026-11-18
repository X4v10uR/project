from collections.abc import Mapping
from zoneinfo import available_timezones

from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, SetPasswordForm
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import team_workflows as flows
from .avatar_utils import (
    build_user_avatar_path,
    get_avatar_background_options,
    get_avatar_sections,
    is_valid_avatar_choice,
    normalize_avatar_background,
    normalize_avatar_choice,
)
from .forms import (
    AccountDeletionForm,
    BillingSettingsForm,
    CustomUserCreationForm,
    PreferencesSettingsForm,
    ProfileSettingsForm,
    TeamCreateForm,
    TeamInviteForm,
)
from .models import User
from .services import resolve_invite, send_team_invite_email
from .security import audit, mark_verified, require_recent, verify_factor, throttle


TIMEZONES = tuple(sorted(available_timezones()))


def account_user(user):
    return {
        'id': user.pk,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'display_name': user.display_name,
        'avatar_url': user.avatar_url,
        'avatar_background_color': user.avatar_background_color,
        'preferred_currency': user.preferred_currency,
        'has_usable_password': user.has_usable_password(),
    }


def payload(request):
    if not isinstance(request.data, Mapping):
        raise ValidationError({'detail': 'Send a JSON object with the form fields.'})
    return request.data


def validated(form):
    if not form.is_valid():
        raise ValidationError({
            field: [str(error) for error in errors] for field, errors in form.errors.items()
        })
    return form


class CsrfSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        session = super().authenticate(request)
        if session is None and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            self.enforce_csrf(request)
        return session


class PublicAccountView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [CsrfSessionAuthentication]


class AccountView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [SessionAuthentication]

    def handle_exception(self, exc):
        if isinstance(exc, flows.TeamActionError):
            return Response({'detail': str(exc)}, status=exc.status_code)
        return super().handle_exception(exc)


class SessionView(PublicAccountView):
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = account_user(request.user) if request.user.is_authenticated else None
        return Response({'user': user}, headers={'Cache-Control': 'no-store'})


class LoginView(PublicAccountView):
    def post(self, request):
        data = payload(request)
        throttle('login:' + (request.META.get('REMOTE_ADDR') or 'unknown'))
        form = validated(AuthenticationForm(request, data={
            'username': data.get('email'),
            'password': data.get('password'),
        }))
        user = form.get_user()
        verify_factor(user, data.get('otp'))
        login(request, user)
        mark_verified(request, user)
        audit(user, 'login.succeeded')
        return Response({'user': account_user(user)})


class SignupView(PublicAccountView):
    def post(self, request):
        form = validated(CustomUserCreationForm(payload(request)))
        user = form.save()
        login(request, user)
        return Response({'user': account_user(user)}, status=201)


class LogoutView(PublicAccountView):
    def post(self, request):
        logout(request)
        return Response(status=204)


class SettingsView(AccountView):
    def get(self, request):
        user = request.user
        return Response({
            'user': account_user(user),
            'profile': {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'display_name': user.display_name,
                'email': user.email,
                'bio': user.bio,
                'timezone': user.timezone,
                'preferred_currency': user.preferred_currency,
                'avatar_choice': build_user_avatar_path(user),
                'avatar_background': user.avatar_background,
            },
            'billing': {
                'subscription_plan': 'free',
                'plan_status': 'active',
                'plan_renews_on': None,
            },
            'preferences': {
                'product_updates_enabled': user.product_updates_enabled,
                'marketing_emails_enabled': user.marketing_emails_enabled,
            },
            'timezones': TIMEZONES if user.timezone in TIMEZONES else (user.timezone, *TIMEZONES),
            'plans': User.PLAN_CHOICES,
            'plan_statuses': User.PLAN_STATUS_CHOICES,
        })


class SettingsSectionView(AccountView):
    def post(self, request, section):
        data = payload(request)
        user = request.user
        if section == 'billing':
            return Response({'detail': 'Subly is free. Plan details are managed by the service.'}, status=403)
        form_class = {
            'profile': ProfileSettingsForm,
            'billing': BillingSettingsForm,
            'preferences': PreferencesSettingsForm,
        }.get(section)
        if form_class:
            previous_email = user.email
            validated(form_class(data, instance=user)).save()
            if user.email != previous_email:
                audit(user, 'email.changed')
        elif section == 'password':
            password_form = PasswordChangeForm if user.has_usable_password() else SetPasswordForm
            user = validated(password_form(user, data)).save()
            update_session_auth_hash(request, user)
            request.session.pop('reauthenticated_at', None)
            audit(user, 'password.changed')
        elif section == 'delete':
            validated(AccountDeletionForm(data, user=user))
            flows.delete_user_account(user)
            logout(request)
            return Response(status=204)
        else:
            return Response({'detail': 'Unknown settings section.'}, status=404)
        return Response({'user': account_user(user)})


class AvatarView(AccountView):
    def get(self, request):
        return Response({
            'sections': get_avatar_sections(),
            'backgrounds': get_avatar_background_options(),
        })

    def post(self, request):
        data = payload(request)
        choice = data.get('avatar_choice', '')
        background = data.get('avatar_background', '')
        if not isinstance(choice, str) or not isinstance(background, str):
            raise ValidationError({'detail': 'Enter a valid avatar and background.'})
        choice = normalize_avatar_choice(choice)
        if choice and not is_valid_avatar_choice(choice):
            raise ValidationError({'avatar_choice': ['Please select a valid avatar.']})
        user = request.user
        if choice:
            user.avatar_choice = choice
        user.avatar_background = normalize_avatar_background(background)
        user.save(update_fields=['avatar_choice', 'avatar_background'])
        return Response({
            'user': account_user(user),
            'avatar_choice': build_user_avatar_path(user),
            'avatar_background': user.avatar_background,
        })


def team_subscription(subscription):
    return {
        'id': subscription.pk,
        'team_id': subscription.team_id,
        'team_name': subscription.team.name,
        'service_name': subscription.service_name,
        'category': subscription.category,
        'currency': subscription.currency,
        'cost': str(subscription.price_on(timezone.localdate())),
        'billing_cycle': subscription.billing_cycle,
        'trial_end_date': subscription.trial_end_date,
        'cancel_by_date': subscription.cancel_by_date,
        'status': subscription.status,
        'icon': subscription.get_fallback_icon(),
        'account_email': subscription.account_email,
        'has_password': bool(subscription.account_password),
    }


class TeamsView(AccountView):
    def get(self, request):
        data = flows.teams_overview_data(request.user)
        return Response({
            'teams': [
                {
                    'id': card['team'].pk,
                    'name': card['team'].name,
                    'role': card['role'],
                    'member_count': card['member_count'],
                    'accent_color': card['accent_color'],
                }
                for card in data['team_cards']
            ],
            'subscriptions': [
                {
                    **team_subscription(row['subscription']),
                    'accent_color': row['accent_color'],
                }
                for row in data['team_subscription_rows']
            ],
            'monthly_spend': str(data['teams_monthly_spend']),
            'monthly_spend_by_currency': {
                currency: str(amount) for currency, amount in data['teams_monthly_spend_by_currency'].items()
            },
        })

    def post(self, request):
        form = validated(TeamCreateForm(payload(request)))
        team = flows.create_team(name=form.cleaned_data['name'], user=request.user)
        return Response({'id': team.pk, 'name': team.name}, status=201)


class TeamDetailView(AccountView):
    def get(self, request, team_id):
        data = flows.team_detail_data(request.user, team_id)
        team = data['team']
        return Response({
            'id': team.pk,
            'name': team.name,
            'role': data['membership'].role,
            'accent_color': data['team_accent_color'],
            'subscriptions': [team_subscription(sub) for sub in data['team_subscriptions']],
            'members': [
                {
                    'id': member.pk,
                    'user_id': member.user_id,
                    'email': member.user.email,
                    'role': member.role,
                    'avatar_url': member.user.avatar_url,
                    'avatar_background_color': member.user.avatar_background_color,
                }
                for member in data['team_members']
            ],
            'pending_requests': [
                {
                    'id': item.pk,
                    'service_name': (item.payload or {}).get('service_name') or 'Subscription request',
                    'requested_by': item.requested_by.email,
                    'created_at': item.created_at,
                }
                for item in data['pending_requests']
            ],
        })

    def delete(self, request, team_id):
        team = flows.get_team_or_404_for_user(request.user, team_id)
        return Response({'message': flows.delete_team(team=team, actor=request.user)})


class TeamMemberView(AccountView):
    def delete(self, request, team_id, membership_id):
        team = flows.get_team_or_404_for_user(request.user, team_id)
        message = flows.remove_team_member(team=team, membership_id=membership_id, actor=request.user)
        return Response({'message': message})


class TeamLeaveView(AccountView):
    def post(self, request, team_id):
        team = flows.get_team_or_404_for_user(request.user, team_id)
        return Response({'message': flows.leave_team(team=team, user=request.user)})


class TeamInviteView(AccountView):
    def post(self, request, team_id):
        team = flows.get_team_or_404_for_user(request.user, team_id)
        form = validated(TeamInviteForm(payload(request)))
        result = flows.invite_team_member(
            team=team, actor=request.user, send_invite=send_team_invite_email, **form.cleaned_data
        )
        return Response(result, status=201)


class TeamSubscriptionPasswordView(AccountView):
    def post(self, request, team_id, subscription_id):
        team = flows.get_team_or_404_for_user(request.user, team_id)
        require_recent(request)
        password = flows.reveal_team_subscription_password(team=team, subscription_id=subscription_id)
        audit(request.user, 'credentials.revealed', f'Subscription {subscription_id}')
        return Response({'password': password}, headers={'Cache-Control': 'no-store'})


class TeamRequestReviewView(AccountView):
    def post(self, request, request_id, action):
        data = payload(request)
        if action not in ('approve', 'reject'):
            return Response({'detail': 'Unknown request action.'}, status=404)
        note = data.get('decision_note', '')
        if not isinstance(note, str):
            raise ValidationError({'decision_note': ['Enter a text note.']})
        team_request = flows.review_team_request(
            request_id=request_id,
            reviewer=request.user,
            approve=action == 'approve',
            decision_note=note,
        )
        return Response({'status': team_request.status})


def invite_details(invite, user):
    if not invite:
        return {'status': 'invalid'}
    return {
        'status': flows.invite_access_status(invite, user),
        'team_id': invite.team_id,
        'team_name': invite.team.name,
        'role': invite.role,
        'email': invite.email,
        'current_email': user.email if user.is_authenticated else None,
    }


class AcceptInviteView(PublicAccountView):
    def get(self, request, token):
        return Response(invite_details(resolve_invite(token), request.user), headers={'Cache-Control': 'no-store'})

    def post(self, request, token):
        payload(request)
        result = flows.redeem_invite(token=token, user=request.user)
        status = result['result']
        invite = result['invite']
        headers = {'Cache-Control': 'no-store'}
        if status not in ('accepted', 'already_member'):
            details = invite_details(invite, request.user)
            messages = {
                'sign_in_required': 'Sign in with the invited email to accept this invitation.',
                'email_mismatch': 'Switch to the invited account before accepting this invitation.',
                'expired': 'This invitation has expired. Ask the team owner for a new link.',
                'revoked': 'This invitation has been revoked.',
                'already_used': 'This invitation has already been used.',
                'invalid': 'This invitation is invalid.',
            }
            status_code = {
                'sign_in_required': 403, 'email_mismatch': 409, 'already_used': 409,
                'expired': 410, 'revoked': 410, 'invalid': 404,
            }.get(status, 400)
            return Response(
                {**details, 'status': status, 'detail': messages.get(status, 'Unable to accept the invitation.')},
                status=status_code, headers=headers,
            )

        user = result['user']
        if status == 'accepted':
            flows.notify_invite_accepted(invite=invite, membership=result['membership'], user=user)
        if not request.user.is_authenticated:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return Response({'status': status, 'team_id': invite.team_id, 'user': account_user(user)}, headers=headers)
