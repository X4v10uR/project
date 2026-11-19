from zoneinfo import available_timezones

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .avatar_utils import (
    build_user_avatar_path,
    get_avatar_background_color,
    get_avatar_background_options,
    get_avatar_sections,
    is_valid_avatar_choice,
    normalize_avatar_background,
    normalize_avatar_choice,
)
from .forms import (
    AccountDeletionForm,
    BillingSettingsForm,
    PreferencesSettingsForm,
    ProfileSettingsForm,
)
from .team_workflows import TeamActionError, delete_user_account
from .security import update_authenticated_session


SETTINGS_SECTION_MAP = {
    'profile': 'profile',
    'billing': 'plan',
    'preferences': 'preferences',
    'password': 'password',
    'delete_account': 'danger',
}

TIMEZONE_CHOICES = tuple(sorted(available_timezones()))


@login_required
def account_settings(request):
    profile_form = ProfileSettingsForm(instance=request.user)
    billing_form = BillingSettingsForm(instance=request.user)
    billing_form.initial.update(subscription_plan='free', plan_status='active', plan_renews_on=None)
    for field in billing_form.fields.values():
        field.disabled = True
    preferences_form = PreferencesSettingsForm(instance=request.user)
    delete_form = AccountDeletionForm(user=request.user)
    password_form_class = PasswordChangeForm if request.user.has_usable_password() else SetPasswordForm
    password_form = password_form_class(user=request.user)
    active_settings_section = 'profile'

    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        active_settings_section = SETTINGS_SECTION_MAP.get(form_type, 'profile')

        if form_type == 'profile':
            profile_form = ProfileSettingsForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                return redirect(f"{reverse('accounts:settings')}?updated=profile")

        if form_type == 'billing':
            return JsonResponse({'detail': 'Subly is free. Plan details are read-only.'}, status=403)

        if form_type == 'preferences':
            preferences_form = PreferencesSettingsForm(request.POST, instance=request.user)
            if preferences_form.is_valid():
                preferences_form.save()
                return redirect(f"{reverse('accounts:settings')}?updated=preferences")

        if form_type == 'password':
            password_form = password_form_class(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_authenticated_session(request, user)
                return redirect(f"{reverse('accounts:settings')}?updated=password")

        if form_type == 'delete_account':
            delete_form = AccountDeletionForm(request.POST, user=request.user)
            if delete_form.is_valid():
                try:
                    delete_user_account(request.user)
                except TeamActionError as error:
                    delete_form.add_error(None, str(error))
                else:
                    logout(request)
                    messages.success(request, 'Your account has been deleted.')
                    return redirect('landing')

    updated = request.GET.get('updated', '')
    active_settings_section = SETTINGS_SECTION_MAP.get(updated, active_settings_section)
    selected_timezone = (profile_form['timezone'].value() or request.user.timezone or 'UTC').strip()

    selected_avatar_choice = normalize_avatar_choice(profile_form['avatar_choice'].value() or '')
    if not is_valid_avatar_choice(selected_avatar_choice):
        selected_avatar_choice = build_user_avatar_path(request.user)
    selected_avatar_background = normalize_avatar_background(
        profile_form['avatar_background'].value() or getattr(request.user, 'avatar_background', '')
    )
    avatar_sections = get_avatar_sections()
    avatar_background_options = get_avatar_background_options()

    if selected_timezone and selected_timezone not in TIMEZONE_CHOICES:
        timezone_choices = (selected_timezone,) + TIMEZONE_CHOICES
    else:
        timezone_choices = TIMEZONE_CHOICES

    return render(
        request,
        'accounts/settings.html',
        {
            'profile_form': profile_form,
            'billing_form': billing_form,
            'preferences_form': preferences_form,
            'delete_form': delete_form,
            'password_form': password_form,
            'profile_updated': updated == 'profile',
            'billing_updated': updated == 'billing',
            'preferences_updated': updated == 'preferences',
            'password_updated': updated == 'password',
            'password_mode': 'change' if request.user.has_usable_password() else 'set',
            'active_settings_section': active_settings_section,
            'updated_form': updated,
            'timezone_choices': timezone_choices,
            'avatar_sections': avatar_sections,
            'selected_avatar_choice': selected_avatar_choice,
            'avatar_background_options': avatar_background_options,
            'selected_avatar_background': selected_avatar_background,
            'selected_avatar_background_color': get_avatar_background_color(selected_avatar_background),
            'hide_global_notifications': True,
            'suppress_base_messages': True,
        },
    )


@login_required
@require_POST
def update_avatar(request):
    avatar_choice = normalize_avatar_choice(request.POST.get('avatar_choice') or '')
    avatar_background = normalize_avatar_background(request.POST.get('avatar_background') or '')

    if avatar_choice and not is_valid_avatar_choice(avatar_choice):
        return JsonResponse({'ok': False, 'error': 'invalid_avatar_choice'}, status=400)

    user = request.user
    update_fields = []
    if avatar_choice and avatar_choice != user.avatar_choice:
        user.avatar_choice = avatar_choice
        update_fields.append('avatar_choice')
    if avatar_background != user.avatar_background:
        user.avatar_background = avatar_background
        update_fields.append('avatar_background')

    if update_fields:
        user.save(update_fields=update_fields)

    return JsonResponse(
        {
            'ok': True,
            'avatar_choice': build_user_avatar_path(user),
            'avatar_background': user.avatar_background,
            'avatar_background_color': get_avatar_background_color(user.avatar_background),
            'avatar_url': user.avatar_url,
        }
    )
