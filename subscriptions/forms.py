from django import forms
from .models import Subscription, Card

class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ['nickname', 'last4', 'brand']
        widgets = {
            'nickname': forms.TextInput(attrs={'placeholder': 'e.g. Work Amex'}),
            'last4': forms.TextInput(attrs={'placeholder': '1234', 'maxlength': '4', 'pattern': '\\d{4}'}),
            'brand': forms.TextInput(attrs={'placeholder': 'e.g. Visa'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
            })
        
        # Add specific styling for last4 field to accommodate the visual prefix
        # 3 groups of 4 dots + spacing takes up about 9rem
        self.fields['last4'].widget.attrs['style'] = 'padding-left: 9.5rem;'

class SubscriptionForm(forms.ModelForm):

    card = forms.ModelChoiceField(
        queryset=Card.objects.none(),
        required=False,
        empty_label="Select a card (optional)",
        widget=forms.Select(attrs={'class': 'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'})
    )

    class Meta:
        model = Subscription
        fields = ['service_name', 'plan_name', 'category', 'billing_cycle', 'cost', 'currency', 'start_date', 'renewal_time', 'status', 'reminders_enabled', 'card', 'notes', 'is_shared', 'split_type', 'account_email', 'account_password']
        widgets = {
            'plan_name': forms.TextInput(attrs={'placeholder': 'e.g. Premium 4K, Family'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'renewal_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'is_shared': forms.RadioSelect(choices=[(False, 'Just me'), (True, 'Shared')]),
            'split_type': forms.RadioSelect(attrs={'class': 'sr-only peer'}),
            'account_email': forms.EmailInput(attrs={'placeholder': 'e.g. user@example.com'}),
            'account_password': forms.PasswordInput(render_value=False, attrs={'placeholder': 'Enter account password'}),
        }

    def __init__(self, *args, **kwargs):
        # user must be passed as kwarg if we want to filter cards by user
        # But Django generic views don't pass user to form kwargs by default easily without overriding get_form_kwargs
        # We can also filter in the view, but let's try to grab it if possible or handle it flexibly.
        # Actually, best practice in Views is to pass 'user' to __init__ if needed. 
        # But wait, subscription_create view manualy initializes the form.
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if self.user:
            self.fields['card'].queryset = Card.objects.filter(user=self.user)
        
        for name, field in self.fields.items():
            if name not in ['card', 'is_shared', 'split_type']: 
                field.widget.attrs.update({
                    'class': 'appearance-none block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
                })
        
        # Add help text for renewal_time field
        self.fields['renewal_time'].help_text = "Setting the time defines the exact time subscription is ending. Notifications will be sent at this time 3 days before renewal."

    def clean_account_password(self):
        account_password = self.cleaned_data.get('account_password')

        if account_password:
            return account_password

        if self.instance and self.instance.pk:
            # Preserve existing encrypted value when edit form is submitted blank.
            return self.instance.account_password

        return None
