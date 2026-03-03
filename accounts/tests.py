from django.test import TestCase, Client
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from accounts.models import Team, TeamInvite, TeamMembership
from accounts.services import create_team_invite
from subscriptions.models import InAppNotification, Subscription, TeamSubscriptionRequest

User = get_user_model()


class SignupViewTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signup_get_renders_form(self):
        response = self.client.get(reverse('accounts:signup'))
        self.assertEqual(response.status_code, 200)

    def test_signup_valid_creates_user_and_logs_in(self):
        response = self.client.post(reverse('accounts:signup'), {
            'email': 'new@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertRedirects(response, reverse('dashboard:home'))
        self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_signup_duplicate_email_fails(self):
        User.objects.create_user(email='dup@example.com', password='password')
        response = self.client.post(reverse('accounts:signup'), {
            'email': 'dup@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 200)  # re-renders form
        self.assertEqual(User.objects.filter(email='dup@example.com').count(), 1)


class LoginLogoutTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email='login@example.com', password='password')

    def test_login_page_renders(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_login_valid_credentials(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'login@example.com',  # Django login uses 'username' field
            'password': 'password',
        })
        self.assertEqual(response.status_code, 302)

    def test_logout_redirects(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)


class AuthRequiredTest(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_subscription_list_requires_login(self):
        response = self.client.get(reverse('subscriptions:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)


class SettingsViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='settings@example.com',
            password='OldStrongPass123!',
            first_name='Old',
            last_name='Name',
        )

    def test_settings_requires_login(self):
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_settings_get_renders_forms(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('accounts:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Save profile')
        self.assertContains(response, 'Change password')

    def test_profile_settings_post_updates_user(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:settings'),
            {
                'form_type': 'profile',
                'first_name': 'New',
                'last_name': 'Display',
                'email': 'new-email@example.com',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=profile', response.url)

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'New')
        self.assertEqual(self.user.last_name, 'Display')
        self.assertEqual(self.user.email, 'new-email@example.com')

    def test_password_settings_post_changes_password_and_keeps_session(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('accounts:settings'),
            {
                'form_type': 'password',
                'old_password': 'OldStrongPass123!',
                'new_password1': 'NewStrongPass456!',
                'new_password2': 'NewStrongPass456!',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=password', response.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass456!'))

        dashboard_response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(dashboard_response.status_code, 200)


class UserManagerTest(TestCase):
    def test_create_superuser_requires_staff_and_superuser_flags(self):
        with self.assertRaisesMessage(ValueError, 'Superuser must have is_staff=True.'):
            User.objects.create_superuser(
                email='badstaff@example.com',
                password='password',
                is_staff=False,
            )

        with self.assertRaisesMessage(ValueError, 'Superuser must have is_superuser=True.'):
            User.objects.create_superuser(
                email='badsuper@example.com',
                password='password',
                is_superuser=False,
            )


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TeamInviteFlowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(email='owner-team@example.com', password='password')
        self.member = User.objects.create_user(email='member-team@example.com', password='password')
        self.other_user = User.objects.create_user(email='other-team@example.com', password='password')

        self.team = Team.objects.create(name='Alpha Team', created_by=self.owner)
        TeamMembership.objects.create(team=self.team, user=self.owner, role=TeamMembership.ROLE_OWNER)

        self.team_subscription = Subscription.objects.create(
            user=self.owner,
            team=self.team,
            service_name='Netflix',
            category='Streaming',
            billing_cycle='monthly',
            cost='10.00',
            start_date=timezone.localdate(),
            status='active',
            account_email='stream@example.com',
            account_password='secret-password',
        )

    def test_team_create_view_creates_owner_membership(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('accounts:team_create'), {'name': 'New Team'})
        self.assertEqual(response.status_code, 302)
        new_team = Team.objects.get(name='New Team')
        self.assertTrue(
            TeamMembership.objects.filter(
                team=new_team,
                user=self.member,
                role=TeamMembership.ROLE_OWNER,
            ).exists()
        )

    def test_accept_invite_requires_matching_email(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        self.client.force_login(self.other_user)
        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Email mismatch')
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.other_user).exists())

        self.client.force_login(self.member)
        post_response = self.client.post(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(post_response.status_code, 302)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)

    def test_expired_invite_cannot_be_accepted(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )
        TeamInvite.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - timedelta(hours=1))

        self.client.force_login(self.member)
        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invite expired')
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

    def test_team_invite_rolls_back_when_email_send_fails(self):
        self.client.force_login(self.owner)
        invitee_email = 'new-person@example.com'

        with patch('accounts.views.send_team_invite_email', side_effect=RuntimeError('smtp failed')):
            response = self.client.post(
                reverse('accounts:team_invite', args=[self.team.pk]),
                {
                    'email': invitee_email,
                    'role': TeamMembership.ROLE_MEMBER,
                },
            )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            TeamInvite.objects.filter(team=self.team, email__iexact=invitee_email).exists()
        )

    def test_duplicate_active_invite_is_blocked(self):
        self.client.force_login(self.owner)
        invitee_email = 'pending@example.com'

        first = self.client.post(
            reverse('accounts:team_invite', args=[self.team.pk]),
            {
                'email': invitee_email,
                'role': TeamMembership.ROLE_MEMBER,
            },
        )
        second = self.client.post(
            reverse('accounts:team_invite', args=[self.team.pk]),
            {
                'email': invitee_email,
                'role': TeamMembership.ROLE_MEMBER,
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            TeamInvite.objects.filter(
                team=self.team,
                email__iexact=invitee_email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).count(),
            1,
        )

    def test_invite_accept_does_not_accept_additional_invite_for_existing_member(self):
        invite_one, token_one = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )
        invite_two, token_two = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        self.client.force_login(self.member)
        first_response = self.client.post(reverse('accounts:invite_accept', args=[token_one]))
        second_response = self.client.post(reverse('accounts:invite_accept', args=[token_two]))

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)

        invite_one.refresh_from_db()
        invite_two.refresh_from_db()
        self.assertIsNotNone(invite_one.accepted_at)
        self.assertIsNone(invite_two.accepted_at)
        self.assertIsNotNone(invite_two.revoked_at)

    def test_team_detail_hides_password_for_non_owner(self):
        self.client.force_login(self.member)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

        response = self.client.get(reverse('accounts:team_detail', args=[self.team.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse(
                'accounts:team_subscription_password',
                args=[self.team.pk, self.team_subscription.pk],
            ),
        )
        self.assertContains(response, 'Password: Hidden')
        self.assertNotContains(response, 'secret-password')

    def test_team_owner_can_fetch_team_subscription_password(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                'accounts:team_subscription_password',
                args=[self.team.pk, self.team_subscription.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(payload['password'], 'secret-password')

    def test_non_owner_cannot_fetch_team_subscription_password(self):
        self.client.force_login(self.member)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

        response = self.client.post(
            reverse(
                'accounts:team_subscription_password',
                args=[self.team.pk, self.team_subscription.pk],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()['ok'])

    def test_team_owner_can_delete_team(self):
        self.client.force_login(self.owner)

        response = self.client.post(reverse('accounts:team_delete', args=[self.team.pk]))

        self.assertRedirects(
            response,
            reverse('accounts:teams_overview'),
            fetch_redirect_response=False,
        )
        self.assertFalse(Team.objects.filter(pk=self.team.pk).exists())
        self.assertFalse(Subscription.objects.filter(pk=self.team_subscription.pk).exists())

    def test_non_owner_cannot_delete_team(self):
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)
        self.client.force_login(self.member)

        response = self.client.post(reverse('accounts:team_delete', args=[self.team.pk]))

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(Team.objects.filter(pk=self.team.pk).exists())

    def test_owner_removes_member_only_removed_member_gets_notification(self):
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)
        owner_two = User.objects.create_user(email='owner-two@example.com', password='password')
        TeamMembership.objects.create(team=self.team, user=owner_two, role=TeamMembership.ROLE_OWNER)

        target_membership = TeamMembership.objects.get(team=self.team, user=self.member)

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('accounts:team_member_remove', args=[self.team.pk, target_membership.pk])
        )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

        removed_notifications = InAppNotification.objects.filter(
            recipient=self.member,
            team=self.team,
            event_type='team.member.removed',
        )
        self.assertEqual(removed_notifications.count(), 1)
        self.assertEqual(
            InAppNotification.objects.filter(
                team=self.team,
                event_type='team.member.removed',
            ).exclude(recipient=self.member).count(),
            0,
        )

    def test_member_leaves_only_owners_get_notified(self):
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)
        owner_two = User.objects.create_user(email='owner-two-leave@example.com', password='password')
        TeamMembership.objects.create(team=self.team, user=owner_two, role=TeamMembership.ROLE_OWNER)
        plain_member = User.objects.create_user(email='plain-member@example.com', password='password')
        TeamMembership.objects.create(team=self.team, user=plain_member, role=TeamMembership.ROLE_MEMBER)

        self.client.force_login(self.member)
        response = self.client.post(reverse('accounts:team_leave', args=[self.team.pk]))

        self.assertRedirects(
            response,
            reverse('accounts:teams_overview'),
            fetch_redirect_response=False,
        )
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

        notified_owner_ids = set(
            InAppNotification.objects.filter(
                team=self.team,
                event_type='team.member.left',
            ).values_list('recipient_id', flat=True)
        )
        self.assertEqual(notified_owner_ids, {self.owner.id, owner_two.id})
        self.assertFalse(
            InAppNotification.objects.filter(
                recipient=plain_member,
                team=self.team,
                event_type='team.member.left',
            ).exists()
        )

    def test_owner_can_leave_when_another_owner_exists(self):
        TeamMembership.objects.create(
            team=self.team,
            user=self.other_user,
            role=TeamMembership.ROLE_OWNER,
        )

        self.client.force_login(self.owner)
        response = self.client.post(reverse('accounts:team_leave', args=[self.team.pk]))

        self.assertRedirects(
            response,
            reverse('accounts:teams_overview'),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            TeamMembership.objects.filter(team=self.team, user=self.owner).exists()
        )
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.other_user,
                team=self.team,
                event_type='team.member.left',
            ).exists()
        )

    def test_last_owner_cannot_leave_team(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('accounts:team_leave', args=[self.team.pk]))

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            TeamMembership.objects.filter(team=self.team, user=self.owner).exists()
        )

    def test_non_owner_cannot_create_team_subscription(self):
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)
        self.client.force_login(self.member)

        response = self.client.post(
            reverse('subscriptions:create'),
            {
                'team_id': str(self.team.pk),
                'service_name': 'Canva',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '14.99',
                'currency': 'USD',
                'start_date': timezone.localdate().isoformat(),
                'status': 'active',
                'is_shared': 'False',
                'split_type': 'equal',
            },
        )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertFalse(
            Subscription.objects.filter(
                team=self.team,
                service_name='Canva',
            ).exists()
        )


class TeamRequestAuthorizationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(email='owner-request@example.com', password='password')
        self.member = User.objects.create_user(email='member-request@example.com', password='password')
        self.outsider = User.objects.create_user(email='outsider-request@example.com', password='password')

        self.team = Team.objects.create(name='Request Team', created_by=self.owner)
        TeamMembership.objects.create(team=self.team, user=self.owner, role=TeamMembership.ROLE_OWNER)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

        self.pending_request = TeamSubscriptionRequest.objects.create(
            team=self.team,
            requested_by=self.member,
            payload={
                'service_name': 'Figma',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '12.00',
                'start_date': timezone.localdate().isoformat(),
                'status': 'active',
                'currency': 'USD',
            },
        )

    def test_non_owner_approve_redirects_to_overview(self):
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse('accounts:team_request_approve', args=[self.pending_request.pk])
        )
        self.assertRedirects(
            response,
            reverse('accounts:teams_overview'),
            fetch_redirect_response=False,
        )
        self.pending_request.refresh_from_db()
        self.assertEqual(self.pending_request.status, TeamSubscriptionRequest.STATUS_PENDING)

    def test_non_owner_reject_redirects_to_overview(self):
        self.client.force_login(self.outsider)
        response = self.client.post(
            reverse('accounts:team_request_reject', args=[self.pending_request.pk]),
            {'decision_note': 'Nope'},
        )
        self.assertRedirects(
            response,
            reverse('accounts:teams_overview'),
            fetch_redirect_response=False,
        )
        self.pending_request.refresh_from_db()
        self.assertEqual(self.pending_request.status, TeamSubscriptionRequest.STATUS_PENDING)
