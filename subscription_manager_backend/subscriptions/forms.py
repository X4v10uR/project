import re
from datetime import date, timedelta

from django import forms
from django.db.models import Q
from django.utils import timezone

from .color_utils import normalize_subscription_display_color
from .models import Card, Subscription


INPUT_CLASSES = (
    'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-lg '
    'shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 '
    'focus:border-indigo-500 sm:text-sm'
)


class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ['nickname', 'last4', 'brand']
        widgets = {
            'nickname': forms.TextInput(attrs={'placeholder': 'e.g. Work Amex'}),
            'last4': forms.TextInput(
                attrs={'placeholder': '1234', 'maxlength': '4', 'pattern': '\\d{4}'},
            ),
            'brand': forms.TextInput(attrs={'placeholder': 'e.g. Visa'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': INPUT_CLASSES})

        # Leave room for the masked digits displayed before the input.
        self.fields['last4'].widget.attrs['style'] = 'padding-left: 9.5rem;'


class SubscriptionForm(forms.ModelForm):
    account_email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'placeholder': 'e.g. user@example.com'}),
    )

    card = forms.ModelChoiceField(
        queryset=Card.objects.none(),
        required=False,
        empty_label="Select a card (optional)",
        widget=forms.Select(attrs={'class': INPUT_CLASSES}),
    )

    class Meta:
        model = Subscription
        fields = [
            'service_name',
            'display_color',
            'plan_name',
            'category',
            'billing_cycle',
            'cost',
            'currency',
            'start_date',
            'renewal_time',
            'status',
            'reminders_enabled',
            'card',
            'notes',
            'is_shared',
            'split_type',
            'account_email',
            'account_password',
        ]
        widgets = {
            'display_color': forms.HiddenInput(),
            'plan_name': forms.TextInput(attrs={'placeholder': 'e.g. Premium 4K, Family'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'renewal_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'is_shared': forms.RadioSelect(choices=[(False, 'Just me'), (True, 'Shared')]),
            'split_type': forms.RadioSelect(attrs={'class': 'sr-only peer'}),
            'account_password': forms.PasswordInput(
                render_value=False,
                attrs={'placeholder': 'Enter account password'},
            ),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        self.fields['account_password'].strip = False
        if self.user:
            available_cards = Q(user=self.user)
            if self.instance.pk and self.instance.team_id and self.instance.card_id:
                available_cards |= Q(pk=self.instance.card_id)
            self.fields['card'].queryset = Card.objects.filter(available_cards)

        for field_name, field in self.fields.items():
            if field_name not in ['card', 'is_shared', 'split_type', 'display_color']:
                field.widget.attrs.update({'class': INPUT_CLASSES})

        self.fields['renewal_time'].help_text = (
            'Setting the time defines the exact time subscription is ending. '
            'Notifications will be sent at this time 3 days before renewal.'
        )

    def clean_account_email(self):
        account_email = self.cleaned_data.get('account_email')
        if not account_email:
            return None
        return account_email.strip()

    def clean_display_color(self):
        raw_value = self.cleaned_data.get("display_color")
        if not raw_value:
            return ""

        normalized = normalize_subscription_display_color(raw_value)
        if not normalized:
            raise forms.ValidationError("Choose a valid hex color.")
        return normalized

    def clean_currency(self):
        currency = self.cleaned_data["currency"].strip()
        if not re.fullmatch(r"[A-Za-z]{3}", currency):
            raise forms.ValidationError("Enter a three-letter currency code, such as USD.")
        return currency.upper()

    def clean_cost(self):
        cost = self.cleaned_data["cost"]
        if cost < 0:
            raise forms.ValidationError("Cost cannot be negative.")
        return cost

    def clean_start_date(self):
        start_date = self.cleaned_data["start_date"]
        cycle = self.cleaned_data.get("billing_cycle")
        if start_date == date.max or (
            cycle and Subscription(start_date=start_date, billing_cycle=cycle).calculate_renewal_date(
                today=max(timezone.localdate(), start_date + timedelta(days=1)),
            ) is None
        ):
            raise forms.ValidationError("Enter a date that allows the next renewal to be scheduled.")
        return start_date

    def clean_account_password(self):
        account_password = self.cleaned_data.get('account_password')

        if account_password:
            # Fernet adds a header, padding, and base64 encoding before storage.
            if len(account_password.encode('utf-8')) > 319:
                raise forms.ValidationError('Account password is too long to store securely.')
            return account_password

        if self.instance and self.instance.pk:
            # Preserve existing encrypted value when edit form is submitted blank.
            return self.instance.account_password

        return None
