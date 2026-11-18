import hashlib
import secrets
import time
from collections.abc import Mapping

import pyotp
from django import forms
from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from subscriptions.models import Subscription
from .models import AccountSecurity, SecurityEvent


def audit(user, action, detail=''):
    SecurityEvent.objects.create(user=user, action=action, detail=detail[:255])


def secret_value(security):
    return Subscription(account_password=security.encrypted_secret).get_account_password()


def protect_secret(raw):
    container = Subscription()
    container.set_account_password(raw)
    return container.account_password


def throttle(key):
    count = cache.get(key, 0)
    if count >= 10:
        raise PermissionDenied('Too many attempts. Try again in five minutes.')
    cache.set(key, count + 1, 300)


@transaction.atomic
def verify_factor(user, code):
    security = AccountSecurity.objects.select_for_update().filter(user=user, enabled=True).first()
    if not security:
        return
    throttle(f'mfa:{user.pk}')
    code = str(code or '').strip().replace(' ', '')
    digest = hashlib.sha256(code.encode()).hexdigest()
    if digest in security.recovery_hashes:
        security.recovery_hashes.remove(digest)
        security.save(update_fields=['recovery_hashes'])
        audit(user, 'mfa.recovery_used')
        return
    secret = secret_value(security)
    if secret and len(code) == 6 and code.isascii() and code.isdigit():
        totp = pyotp.TOTP(secret)
        step = int(time.time()) // 30
        for candidate in (step - 1, step, step + 1):
            if candidate > security.last_used_step and secrets.compare_digest(totp.at(candidate * 30), code):
                security.last_used_step = candidate
                security.save(update_fields=['last_used_step'])
                return
    raise PermissionDenied('Enter a fresh authenticator code or an unused recovery code.')


def mark_verified(request, user):
    security = AccountSecurity.objects.filter(user=user, enabled=True).first()
    if security:
        request.session['mfa_revision'] = security.revision


def require_recent(request):
    stamp = request.session.get('reauthenticated_at', 0)
    if not 0 <= time.time() - stamp <= 300:
        raise PermissionDenied('Verify your current Subly password before this sensitive action.')


class SecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            security = AccountSecurity.objects.filter(user=request.user, enabled=True).first()
            if security and request.session.get('mfa_revision') != security.revision:
                logout(request)
            elif request.path.endswith('/password/') or request.path.endswith('/password'):
                # All API and legacy credential-reveal routes share this guard.
                if '/subscriptions/' in request.path and request.method == 'POST':
                    try:
                        require_recent(request)
                    except PermissionDenied as exc:
                        return JsonResponse({'detail': str(exc)}, status=403)
        return self.get_response(request)


class SecureAuthenticationForm(AuthenticationForm):
    otp = forms.CharField(required=False, label='Authenticator or recovery code')

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        try:
            verify_factor(user, self.data.get('otp'))
        except PermissionDenied as exc:
            raise forms.ValidationError(str(exc)) from exc
        mark_verified(self.request, user)


class Reauthentication(serializers.Serializer):
    password = serializers.CharField(trim_whitespace=False)
    otp = serializers.CharField(required=False, allow_blank=True)


@api_view(['GET', 'POST'])
def security_settings(request):
    user = request.user
    if request.method == 'GET':
        row = AccountSecurity.objects.filter(user=user, enabled=True).first()
        return Response({'enabled': bool(row), 'recovery_remaining': len(row.recovery_hashes) if row else 0,
            'events': [{'action': event.action, 'detail': event.detail, 'date': event.created_at} for event in user.security_events.all()[:50]]}, headers={'Cache-Control': 'no-store'})
    if not isinstance(request.data, Mapping):
        raise serializers.ValidationError('Send a JSON object.')
    action = request.data.get('action')
    if action == 'reauthenticate':
        data = Reauthentication(data=request.data)
        data.is_valid(raise_exception=True)
        throttle(f'reauth:{user.pk}')
        if not user.check_password(data.validated_data['password']):
            audit(user, 'reauthentication.failed')
            raise PermissionDenied('Current password is incorrect.')
        verify_factor(user, data.validated_data.get('otp'))
        request.session['reauthenticated_at'] = time.time()
        audit(user, 'reauthentication.succeeded')
        return Response({'verified': True})
    require_recent(request)
    if action == 'setup':
        if AccountSecurity.objects.filter(user=user, enabled=True).exists():
            raise serializers.ValidationError('MFA is already enabled.')
        raw = pyotp.random_base32()
        request.session['pending_mfa'] = protect_secret(raw)
        return Response({'secret': raw, 'uri': pyotp.TOTP(raw).provisioning_uri(name=user.email, issuer_name='Subly')}, headers={'Cache-Control': 'no-store'})
    if action == 'enable':
        raw = secret_value(AccountSecurity(encrypted_secret=request.session.get('pending_mfa', '')))
        throttle(f'mfa_setup:{user.pk}')
        step = int(time.time()) // 30
        otp = str(request.data.get('otp', ''))
        matched = next((candidate for candidate in (step - 1, step, step + 1) if raw and otp.isascii() and secrets.compare_digest(pyotp.TOTP(raw).at(candidate * 30), otp)), None)
        if matched is None:
            raise serializers.ValidationError('Enter the code from your authenticator to finish setup.')
        codes = [secrets.token_hex(6) for _ in range(8)]
        row, _ = AccountSecurity.objects.update_or_create(user=user, defaults={'enabled': True,
            'encrypted_secret': protect_secret(raw), 'recovery_hashes': [hashlib.sha256(code.encode()).hexdigest() for code in codes],
            'revision': secrets.token_hex(24), 'last_used_step': matched})
        request.session.pop('pending_mfa', None)
        request.session['mfa_revision'] = row.revision
        audit(user, 'mfa.enabled')
        return Response({'recovery_codes': codes}, headers={'Cache-Control': 'no-store'})
    if action == 'disable':
        verify_factor(user, request.data.get('otp'))
        AccountSecurity.objects.filter(user=user).delete()
        request.session.pop('mfa_revision', None)
        audit(user, 'mfa.disabled')
        return Response({'enabled': False})
    raise serializers.ValidationError('Unknown security action.')
