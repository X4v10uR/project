from django.shortcuts import render, redirect
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse

from .forms import CustomUserCreationForm, ProfileSettingsForm

def signup(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard:home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/signup.html', {'form': form})


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
