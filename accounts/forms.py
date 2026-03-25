from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .avatar_utils import (
    is_valid_avatar_choice,
    normalize_avatar_background,
    normalize_avatar_choice,
)
from .models import Team, TeamMembership, User

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email',)

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = ('email',)


class ProfileSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            'first_name',
            'last_name',
            'display_name',
            'email',
            'avatar_choice',
            'avatar_background',
            'bio',
            'timezone',
            'preferred_currency',
        )

    def clean_avatar_choice(self):
        raw_avatar_choice = self.cleaned_data.get('avatar_choice') or ''
        avatar_choice = normalize_avatar_choice(raw_avatar_choice)

        if not avatar_choice:
            current_choice = normalize_avatar_choice(getattr(self.instance, 'avatar_choice', ''))
            return current_choice

        if not is_valid_avatar_choice(avatar_choice):
            raise forms.ValidationError('Please select a valid avatar from the picker.')

        return avatar_choice

    def clean_avatar_background(self):
        raw_background = self.cleaned_data.get('avatar_background') or ''
        if not raw_background:
            return normalize_avatar_background(getattr(self.instance, 'avatar_background', ''))
        return normalize_avatar_background(raw_background)

    def clean_timezone(self):
        tz = (self.cleaned_data.get('timezone') or 'UTC').strip()
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError as exc:
            raise forms.ValidationError('Enter a valid IANA timezone (e.g. UTC, Europe/London).') from exc
        return tz

    def clean_preferred_currency(self):
        currency = (self.cleaned_data.get('preferred_currency') or '').strip().upper()
        if not currency:
            return 'USD'
        if len(currency) != 3 or not currency.isalpha():
            raise forms.ValidationError('Use a 3-letter currency code (e.g. USD, EUR).')
        return currency


class BillingSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('subscription_plan', 'plan_status', 'plan_renews_on')
        widgets = {
            'plan_renews_on': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        plan = cleaned_data.get('subscription_plan') or User.PLAN_FREE
        status = cleaned_data.get('plan_status') or User.PLAN_STATUS_NONE

        if plan == User.PLAN_FREE:
            cleaned_data['plan_renews_on'] = None
        if status in {User.PLAN_STATUS_NONE, User.PLAN_STATUS_CANCELLED}:
            cleaned_data['plan_renews_on'] = None
        return cleaned_data


class PreferencesSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('product_updates_enabled', 'marketing_emails_enabled')


class AccountDeletionForm(forms.Form):
    confirm_email = forms.EmailField()
    confirm_phrase = forms.CharField(help_text='Type DELETE to confirm account deletion.')
    current_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if self.user and not self.user.has_usable_password():
            self.fields['current_password'].help_text = (
                'No password check is required for invite-link accounts.'
            )

    def clean_confirm_email(self):
        confirm_email = (self.cleaned_data.get('confirm_email') or '').strip().lower()
        if not self.user:
            raise forms.ValidationError('Unable to validate account email.')
        if confirm_email != self.user.email.lower():
            raise forms.ValidationError('Email does not match your account.')
        return confirm_email

    def clean_confirm_phrase(self):
        phrase = (self.cleaned_data.get('confirm_phrase') or '').strip().upper()
        if phrase != 'DELETE':
            raise forms.ValidationError('Type DELETE exactly to confirm deletion.')
        return phrase

    def clean(self):
        cleaned_data = super().clean()
        if not self.user:
            raise forms.ValidationError('Unable to validate account deletion request.')

        if self.user.has_usable_password():
            raw_password = cleaned_data.get('current_password') or ''
            if not raw_password:
                self.add_error('current_password', 'Current password is required.')
            elif not self.user.check_password(raw_password):
                self.add_error('current_password', 'Current password is incorrect.')

        return cleaned_data


class TeamCreateForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ('name',)


class TeamInviteForm(forms.Form):
    email = forms.EmailField()
    role = forms.ChoiceField(choices=TeamMembership.ROLE_CHOICES)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        return email
