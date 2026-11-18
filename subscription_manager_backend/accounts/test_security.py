import time

import pyotp
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from accounts.models import AccountSecurity, User
from accounts.security import protect_secret
from subscriptions.models import Subscription


class SecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('secure@example.test', 'ExamplePassword42!')
        self.client.force_login(self.user)
        self.url = '/api/accounts/security/'

    def post(self, action, **fields):
        return self.client.post(self.url, {'action': action, **fields}, content_type='application/json')

    def reauthenticate(self):
        return self.post('reauthenticate', password='ExamplePassword42!')

    def test_reveal_requires_recent_password_and_records_activity(self):
        sub = Subscription.objects.create(user=self.user, service_name='Vault', cost=5, billing_cycle='monthly', start_date=timezone.localdate(), account_password='secret')
        url = f'/api/subscriptions/{sub.pk}/password/'
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertEqual(self.post('reauthenticate', password='wrong').status_code, 403)
        self.assertEqual(self.reauthenticate().status_code, 200)
        response = self.client.post(url)
        self.assertEqual(response.json()['password'], 'secret')
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertTrue(self.user.security_events.filter(action='credentials.revealed').exists())
        session = self.client.session
        session['reauthenticated_at'] = time.time() - 301
        session.save()
        self.assertEqual(self.client.post(url).status_code, 403)

    def test_setup_enrollment_recovery_and_replay_protection(self):
        self.assertEqual(self.post('setup').status_code, 403)
        self.reauthenticate()
        setup = self.post('setup').json()
        self.assertEqual(self.post('enable', otp='not-a-code').status_code, 400)
        code = pyotp.TOTP(setup['secret']).now()
        result = self.post('enable', otp=code)
        self.assertEqual(result.status_code, 200, result.content)
        codes = result.json()['recovery_codes']
        row = AccountSecurity.objects.get(user=self.user)
        self.assertNotIn(setup['secret'], row.encrypted_secret)
        self.assertNotIn(codes[0], row.recovery_hashes)
        self.client.logout()
        credentials = {'email': self.user.email, 'password': 'ExamplePassword42!'}
        self.assertEqual(self.client.post('/api/accounts/login/', credentials, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post('/api/accounts/login/', {**credentials, 'otp': code}, content_type='application/json').status_code, 403)
        result = self.client.post('/api/accounts/login/', {**credentials, 'otp': codes[0]}, content_type='application/json')
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(self.client.get('/api/accounts/session/').json()['user'])
        self.client.logout()
        self.assertEqual(self.client.post('/api/accounts/login/', {**credentials, 'otp': codes[0]}, content_type='application/json').status_code, 403)

    def test_mfa_invalidates_sessions_that_have_not_passed_second_factor(self):
        AccountSecurity.objects.create(user=self.user, enabled=True, encrypted_secret=protect_secret(pyotp.random_base32()), revision='new-device')
        self.assertIsNone(self.client.get('/api/accounts/session/').json()['user'])

    def test_legacy_login_accepts_factor_and_blocks_missing_factor(self):
        secret = pyotp.random_base32()
        AccountSecurity.objects.create(user=self.user, enabled=True, encrypted_secret=protect_secret(secret), revision='device')
        self.client.logout()
        result = self.client.post('/accounts/login/', {'username': self.user.email, 'password': 'ExamplePassword42!'})
        self.assertEqual(result.status_code, 200)
        result = self.client.post('/accounts/login/', {'username': self.user.email, 'password': 'ExamplePassword42!', 'otp': pyotp.TOTP(secret).now()})
        self.assertEqual(result.status_code, 302)
        self.assertIsNotNone(self.client.get('/api/accounts/session/').json()['user'])

    def test_plan_cannot_be_self_promoted(self):
        response = self.client.post('/api/accounts/settings/billing/', {'subscription_plan': 'business', 'plan_status': 'active'}, content_type='application/json')
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.subscription_plan, 'free')
        self.assertEqual(self.client.post('/accounts/settings/', {'form_type': 'billing', 'subscription_plan': 'business'}).status_code, 403)

    def test_reauthentication_is_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self.post('reauthenticate', password='wrong').status_code, 403)
        response = self.reauthenticate()
        self.assertEqual(response.status_code, 403)
        self.assertIn('Too many attempts', response.json()['detail'])
