from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
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
        fields = ('first_name', 'last_name', 'email')


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
