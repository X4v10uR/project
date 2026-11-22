from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth.models import AnonymousUser
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from subscriptions.models import InAppNotification, Subscription, TeamSubscriptionRequest
from .models import TeamInvite, TeamMembership, User
from .services import create_team_invite
from .team_workflows import create_team, redeem_invite, rotate_team_invite, TeamActionError


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class TeamInvitationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner@example.test')
        self.member = User.objects.create_user('member@example.test')
        self.team = create_team(name='Design', user=self.owner)
        self.membership = TeamMembership.objects.create(team=self.team, user=self.member)
        self.client = APIClient(enforce_csrf_checks=True)
        self.detail = reverse('accounts_api:team_detail', args=[self.team.pk])
        self.send_url = reverse('accounts_api:team_invite', args=[self.team.pk])

    def post(self, url, data=None):
        self.client.get(reverse('accounts_api:session'))
        return self.client.post(url, data or {}, format='json',
                                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def invitation(self, email='new@example.test', role=TeamMembership.ROLE_MEMBER):
        invite, token = create_team_invite(team=self.team, email=email, role=role, invited_by=self.owner)
        return invite, reverse('accounts_api:invite_accept', args=[token])

    def test_new_recipient_sets_password_and_can_sign_in_again(self):
        invite, url = self.invitation()
        self.assertTrue(self.client.get(url).json()['requires_account'])
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        password = 'Invited-Example42!'
        response = self.post(url, {'password1': password, 'password2': password, 'email': 'ignored@example.test'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['user']['has_usable_password'])
        user = User.objects.get(email=invite.email)
        self.assertTrue(user.check_password(password))
        self.assertEqual(self.team.memberships.get(user=user).role, invite.role)
        self.post(reverse('accounts_api:logout'))
        response = self.post(reverse('accounts_api:login'), {'email': invite.email, 'password': password})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(url).json()['status'], 'already_used')

    def test_bad_password_does_not_create_account_or_consume_invite(self):
        invite, url = self.invitation()
        for passwords in (
            {'password1': 'short', 'password2': 'short'},
            {'password1': 'Invited-Example42!', 'password2': 'different'},
            {'password1': '', 'password2': ''},
        ):
            with self.subTest(passwords=passwords):
                response = self.post(url, passwords)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertFalse(User.objects.filter(email=invite.email).exists())
                invite.refresh_from_db()
                self.assertIsNone(invite.accepted_at)

    def test_invitation_cannot_reset_an_existing_accounts_password(self):
        existing = User.objects.create_user('registered@example.test', 'Existing-Example42!')
        invite, url = self.invitation(email=existing.email)
        response = self.post(url, {'password1': 'Invited-Example42!', 'password2': 'Invited-Example42!'})
        self.assertEqual(response.status_code, 403)
        existing.refresh_from_db()
        self.assertTrue(existing.check_password('Existing-Example42!'))
        self.assertFalse(self.team.memberships.filter(user=existing).exists())

    def test_account_created_during_redemption_requires_sign_in(self):
        existing = User.objects.create_user('registered@example.test')
        invite, url = self.invitation()
        token = url.rstrip('/').split('/')[-1]
        with patch('accounts.team_workflows.User.objects.get_or_create', return_value=(existing, False)):
            result = redeem_invite(token=token, user=AnonymousUser())
        self.assertEqual(result['result'], 'sign_in_required')
        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)

    def test_owner_can_resend_revoke_and_recover_from_delivery_failure(self):
        self.client.force_login(self.owner)
        with patch('accounts.api_views.send_team_invite_email', side_effect=RuntimeError('offline')):
            first = self.post(self.send_url, {'email': 'new@example.test', 'role': 'viewer'})
        self.assertEqual(first.status_code, 201, first.content)
        self.assertFalse(first.json()['email_sent'])
        old_token = urlsplit(first.json()['invite_url']).path.rstrip('/').split('/')[-1]
        first_invite = TeamInvite.objects.get(team=self.team)
        detail = self.client.get(self.detail).json()
        self.assertEqual(detail['pending_invites'][0]['email'], 'new@example.test')
        self.assertNotIn('token_hash', detail['pending_invites'][0])
        second = self.post(self.send_url, {'email': 'new@example.test', 'role': 'viewer'})
        self.assertTrue(second.json()['email_sent'])
        self.assertIn(second.json()['invite_url'], mail.outbox[0].body)
        first_invite.refresh_from_db()
        self.assertIsNotNone(first_invite.revoked_at)
        self.client.logout()
        old_url = reverse('accounts_api:invite_accept', args=[old_token])
        self.assertEqual(self.post(old_url).status_code, 410)
        active = TeamInvite.objects.get(team=self.team, revoked_at__isnull=True)
        revoke_url = reverse('accounts_api:team_invite_detail', args=[self.team.pk, active.pk])
        self.client.force_login(self.owner)
        self.client.get(reverse('accounts_api:session'))
        response = self.client.delete(revoke_url, HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(self.detail).json()['pending_invites'], [])
        self.client.logout()
        token = urlsplit(second.json()['invite_url']).path.rstrip('/').split('/')[-1]
        self.assertEqual(self.post(reverse('accounts_api:invite_accept', args=[token])).status_code, 410)
        self.assertFalse(User.objects.filter(email=active.email).exists())

    def test_member_cannot_view_send_or_revoke_invites(self):
        invite, _ = self.invitation()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.detail).json()['pending_invites'], [])
        self.assertEqual(self.post(self.send_url, {'email': 'other@example.test', 'role': 'owner'}).status_code, 403)
        revoke_url = reverse('accounts_api:team_invite_detail', args=[self.team.pk, invite.pk])
        response = self.client.delete(revoke_url, HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 403)
        with self.assertRaises(TeamActionError):
            rotate_team_invite(team=self.team, email=invite.email, role='owner', actor=self.member)
        invite.refresh_from_db()
        self.assertIsNone(invite.revoked_at)

    def test_registered_recipient_can_accept_from_notification_when_email_fails(self):
        recipient = User.objects.create_user('registered@example.test')
        self.client.force_login(self.owner)
        with patch('accounts.api_views.send_team_invite_email', side_effect=RuntimeError('offline')):
            self.post(self.send_url, {'email': recipient.email, 'role': 'accountant'})
        notification = InAppNotification.objects.get(recipient=recipient, event_type='team.invite.received')
        self.assertEqual(notification.link_url, '/accounts/teams/')
        self.client.force_login(recipient)
        received = self.client.get(reverse('accounts_api:teams')).json()['received_invites']
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['role'], 'accountant')
        response = self.post(reverse('accounts_api:received_invite_accept', args=[received[0]['id']]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.team.memberships.get(user=recipient).role, 'accountant')

    def test_registering_after_invitation_still_requires_the_email_token(self):
        invite, url = self.invitation()
        registered = User.objects.create_user(invite.email)
        self.client.force_login(registered)
        self.assertEqual(self.client.get(reverse('accounts_api:teams')).json()['received_invites'], [])
        response = self.post(reverse('accounts_api:received_invite_accept', args=[invite.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.team.memberships.filter(user=registered).exists())
        self.assertEqual(self.post(url).status_code, 200)

    def test_inbox_acceptance_checks_recipient_revocation_and_csrf(self):
        self.client.force_login(self.owner)
        recipient = User.objects.create_user('recipient@example.test')
        self.post(self.send_url, {'email': recipient.email, 'role': 'member'})
        invite = TeamInvite.objects.get(email=recipient.email)
        url = reverse('accounts_api:received_invite_accept', args=[invite.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.post(url).status_code, 404)
        self.client.force_login(recipient)
        self.assertEqual(self.client.post(url).status_code, 403)
        TeamInvite.objects.filter(pk=invite.pk).update(revoked_at=timezone.now())
        self.assertEqual(self.post(url).status_code, 410)
        self.assertFalse(self.team.memberships.filter(user=recipient).exists())

    def test_expired_invites_cannot_create_accounts(self):
        invite, url = self.invitation()
        TeamInvite.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.post(url, {'password1': 'Invited-Example42!', 'password2': 'Invited-Example42!'})
        self.assertEqual(response.status_code, 410)
        self.assertFalse(User.objects.filter(email=invite.email).exists())
        self.client.force_login(self.owner)
        self.assertEqual(self.post(self.send_url, {'email': invite.email, 'role': 'member'}).status_code, 201)
        self.assertEqual(len(self.client.get(self.detail).json()['pending_invites']), 1)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.revoked_at)

    def test_legacy_invite_also_sets_password(self):
        invite, url = self.invitation()
        self.client.get(reverse('accounts_api:session'))
        response = self.client.post(
            url.removeprefix('/api'), {'password1': 'Invited-Example42!', 'password2': 'Invited-Example42!'},
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.get(email=invite.email).check_password('Invited-Example42!'))

    def test_removed_requester_cannot_have_subscription_approved(self):
        pending = TeamSubscriptionRequest.objects.create(team=self.team, requested_by=self.member,
                                                        payload={'service_name': 'Old request', 'cost': '10.00'})
        self.membership.delete()
        self.client.force_login(self.owner)
        url = reverse('accounts_api:request_review', args=[pending.pk, 'approve'])
        response = self.post(url)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(Subscription.objects.filter(team=self.team).exists())
        pending.refresh_from_db()
        self.assertEqual(pending.status, TeamSubscriptionRequest.STATUS_PENDING)
