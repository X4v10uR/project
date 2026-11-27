from urllib.parse import urlsplit

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from subscriptions.models import Subscription, Transaction

from .models import Team, TeamMembership, User
from .services import create_team_invite
from .team_workflows import create_team


class AccountAPITest(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.session_url = reverse('accounts_api:session')

    def test_account_deletion_keeps_shared_team_with_remaining_owner(self):
        password = ' StrongPassword42! '
        creator = User.objects.create_user(email='creator@example.com', password=password)
        other = User.objects.create_user(email='other-owner@example.com')
        team = create_team(name='Shared team', user=creator)
        membership = TeamMembership.objects.create(team=team, user=other, role=TeamMembership.ROLE_MEMBER)
        empty_team = create_team(name='Solo team', user=creator)
        subscription = Subscription.objects.create(
            user=creator, team=team, service_name='Team plan', category='Software',
            billing_cycle='monthly', cost='10.00', start_date=timezone.localdate(),
        )
        charge = Transaction.objects.create(
            user=creator, subscription=subscription, service_name_snapshot='Team plan',
            amount='10.00', currency='USD', charged_for_date=timezone.localdate(),
        )
        self.client.force_login(creator)
        self.client.get(self.session_url)
        endpoint = reverse('accounts_api:settings_section', args=['delete'])
        confirmation = {'confirm_email': creator.email, 'confirm_phrase': 'DELETE', 'current_password': password}

        def delete_account():
            return self.client.post(
                endpoint, confirmation, format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
            )

        blocked = delete_account()
        self.assertEqual(blocked.status_code, 409, blocked.content)
        self.assertIn(team.name, blocked.json()['detail'])
        self.assertTrue(User.objects.filter(pk=creator.pk).exists())
        self.assertTrue(Team.objects.filter(pk=empty_team.pk).exists())

        membership.role = TeamMembership.ROLE_OWNER
        membership.save(update_fields=['role'])
        deleted = delete_account()
        self.assertEqual(deleted.status_code, 204, deleted.content)
        self.assertFalse(User.objects.filter(pk=creator.pk).exists())
        self.assertFalse(Team.objects.filter(pk=empty_team.pk).exists())
        team.refresh_from_db()
        subscription.refresh_from_db()
        charge.refresh_from_db()
        self.assertIsNone(team.created_by_id)
        self.assertEqual(subscription.user_id, other.pk)
        self.assertEqual(charge.user_id, other.pk)
        self.assertEqual(list(team.memberships.values_list('user_id', flat=True)), [other.pk])

    def test_invalid_timezone_path_and_non_ascii_currency_return_field_errors(self):
        user = User.objects.create_user(email='preferences@example.com')
        self.client.force_login(user)
        self.client.get(self.session_url)
        response = self.client.post(
            reverse('accounts_api:settings_section', args=['profile']),
            {'email': user.email, 'timezone': '../UTC', 'preferred_currency': 'ÉUR'},
            format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('timezone', response.json())
        self.assertIn('preferred_currency', response.json())

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

    def test_login_remember_choice_controls_session_expiry(self):
        password = 'R6@fH2kz6dLM'
        user = User.objects.create_user(email='remember@example.com', password=password)
        cases = [
            ({'remember': True}, False, 60 * 60 * 24 * 30),
            ({'remember': False}, True, None),
            ({'remember': 'false'}, True, None),
            ({}, False, None),
        ]
        for choice, browser_session, expiry in cases:
            with self.subTest(choice=choice):
                client = APIClient(enforce_csrf_checks=True)
                client.get(self.session_url)
                response = client.post(
                    reverse('accounts_api:login'),
                    {'email': user.email, 'password': password, **choice},
                    format='json', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(client.session.get_expire_at_browser_close(), browser_session)
                if expiry:
                    self.assertEqual(client.session.get_expiry_age(), expiry)

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
