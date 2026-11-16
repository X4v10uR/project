from urllib.parse import urlsplit

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import TeamMembership, User
from .services import create_team_invite
from .team_workflows import create_team


class AccountAPITest(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.session_url = reverse('accounts_api:session')

    def test_signup_requires_csrf_and_returns_authenticated_session(self):
        url = reverse('accounts_api:signup')
        signup = {
            'email': 'owner@example.com',
            'password1': 'R6@fH2kz6dLM',
            'password2': 'R6@fH2kz6dLM',
        }

        self.assertIsNone(self.client.get(self.session_url).json()['user'])
        self.assertEqual(self.client.post(url, signup, format='json').status_code, 403)
        self.assertFalse(User.objects.filter(email=signup['email']).exists())

        response = self.client.post(
            url, signup, format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get(self.session_url).json()['user']['email'], signup['email'])

    def test_invite_get_is_read_only_and_post_consumes_the_token(self):
        owner = User.objects.create_user(email='owner@example.com')
        team = create_team(name='Design', user=owner)
        invite, token = create_team_invite(
            team=team, email='member@example.com', role=TeamMembership.ROLE_MEMBER, invited_by=owner
        )
        url = reverse('accounts_api:invite_accept', args=[token])

        self.assertEqual(self.client.get(url).json()['status'], 'ready')
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        self.assertIsNone(self.client.get(self.session_url).json()['user'])
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 403)

        response = self.client.post(
            url, {}, format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['team_id'], team.pk)
        self.assertEqual(self.client.get(self.session_url).json()['user']['email'], invite.email)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertEqual(self.client.get(url).json()['status'], 'already_used')

    def test_invitation_cannot_authenticate_an_existing_account(self):
        owner = User.objects.create_user(email='owner@example.com')
        member = User.objects.create_user(email='member@example.com')
        other = User.objects.create_user(email='other@example.com')
        team = create_team(name='Design', user=owner)
        invite, token = create_team_invite(
            team=team, email=member.email, role=TeamMembership.ROLE_MEMBER, invited_by=owner
        )
        url = reverse('accounts_api:invite_accept', args=[token])

        def redeem():
            self.client.get(self.session_url)
            return self.client.post(
                url, {'action': 'switch_account'}, format='json',
                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
            )

        self.assertEqual(redeem().status_code, 403)
        self.assertIsNone(self.client.get(self.session_url).json()['user'])
        self.client.force_login(other)
        self.assertEqual(redeem().status_code, 409)
        self.assertEqual(self.client.get(self.session_url).json()['user']['id'], other.pk)
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)
        self.assertFalse(TeamMembership.objects.filter(team=team, user=member).exists())

        self.client.force_login(member)
        self.assertEqual(redeem().status_code, 200)
        self.assertTrue(TeamMembership.objects.filter(team=team, user=member).exists())

    def test_settings_requires_password_to_change_sign_in_email(self):
        password = 'OldStrongPass123!'
        user = User.objects.create_user(email='profile@example.com', password=password)
        self.client.force_login(user)
        self.client.get(self.session_url)
        headers = {'HTTP_X_CSRFTOKEN': self.client.cookies['csrftoken'].value}
        url = reverse('accounts_api:settings_section', args=['profile'])
        profile = {'email': 'NEW@example.com', 'timezone': 'UTC', 'preferred_currency': 'USD'}
        response = self.client.post(url, profile, format='json', **headers)
        self.assertEqual(response.status_code, 400)
        self.assertIn('current_password', response.json())
        user.refresh_from_db()
        self.assertEqual(user.email, 'profile@example.com')

        response = self.client.post(url, {**profile, 'current_password': password}, format='json', **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['email'], 'new@example.com')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_passwordless_account_can_set_password_with_single_use_email_link(self):
        user = User.objects.create_user(email='invitee@example.com')
        self.assertFalse(user.has_usable_password())
        self.client.get(self.session_url)
        csrf = self.client.cookies['csrftoken'].value
        response = self.client.post(
            reverse('accounts:password_reset'), {'email': user.email}, HTTP_X_CSRFTOKEN=csrf
        )
        self.assertRedirects(response, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        link = next(line for line in mail.outbox[0].body.splitlines() if line.startswith('http'))
        response = self.client.get(urlsplit(link).path)
        self.assertEqual(response.status_code, 302)
        password = 'At6@pRKc3zY8'
        response = self.client.post(
            response.url, {'new_password1': password, 'new_password2': password}, HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))
        user.refresh_from_db()
        self.assertTrue(user.check_password(password))
        self.assertContains(self.client.get(urlsplit(link).path), 'expired or already been used')
