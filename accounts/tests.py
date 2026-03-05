from django.test import TestCase, Client
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
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

    def test_settings_get_for_unusable_password_user_shows_set_password(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=['password'])
        self.client.force_login(self.user)

        response = self.client.get(reverse('accounts:settings'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Set Password')
        self.assertContains(response, 'Set password')

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

    def test_settings_post_sets_password_for_unusable_password_user(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=['password'])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:settings'),
            {
                'form_type': 'password',
                'new_password1': 'MagicPass123!@#',
                'new_password2': 'MagicPass123!@#',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('?updated=password', response.url)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('MagicPass123!@#'))

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

    def test_teams_overview_backfills_missing_creator_membership(self):
        legacy_owner = User.objects.create_user(email='legacy-owner@example.com', password='password')
        legacy_team = Team.objects.create(name='Legacy Team', created_by=legacy_owner)

        self.client.force_login(legacy_owner)
        response = self.client.get(reverse('accounts:teams_overview'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Legacy Team')
        self.assertTrue(
            TeamMembership.objects.filter(
                team=legacy_team,
                user=legacy_owner,
                role=TeamMembership.ROLE_OWNER,
            ).exists()
        )

    def test_team_create_get_renders_create_mode_in_overview_template(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse('accounts:team_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-teams-mode="create"')
        self.assertContains(response, 'Back to Teams')

    def test_team_create_invalid_post_renders_create_mode_with_field_error(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('accounts:team_create'), {'name': ''})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-teams-mode="create"')
        self.assertContains(response, 'This field is required')

    def test_teams_overview_weekly_spend_uses_52_over_12(self):
        self.team_subscription.status = 'paused'
        self.team_subscription.save(update_fields=['status'])

        Subscription.objects.create(
            user=self.owner,
            team=self.team,
            service_name='Weekly Team Service',
            category='Software',
            billing_cycle='weekly',
            cost='12.00',
            start_date=timezone.localdate(),
            status='active',
        )

        self.client.force_login(self.owner)
        response = self.client.get(reverse('accounts:teams_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['teams_monthly_spend'], Decimal('52.00'))

    def test_accept_invite_auto_accepts_for_logged_out_existing_user(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertEqual(invite.accepted_by_id, self.member.pk)

    def test_accept_invite_logged_in_wrong_email_shows_switch_interstitial(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        self.client.force_login(self.other_user)
        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Switch account to continue')
        self.assertContains(response, self.member.email)
        self.assertContains(response, self.other_user.email)
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.other_user).exists())

        invite.refresh_from_db()
        self.assertIsNone(invite.accepted_at)

    def test_accept_invite_switch_account_post_accepts_invite(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse('accounts:invite_accept', args=[raw_token]),
            {'action': 'switch_account'},
        )
        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(int(self.client.session['_auth_user_id']), self.member.pk)
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertEqual(invite.accepted_by_id, self.member.pk)

    def test_accept_invite_auto_creates_user_without_password(self):
        invitee_email = 'new-magic-user@example.com'
        invite, raw_token = create_team_invite(
            team=self.team,
            email=invitee_email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )

        invited_user = User.objects.filter(email__iexact=invitee_email).first()
        self.assertIsNotNone(invited_user)
        self.assertFalse(invited_user.has_usable_password())
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=invited_user).exists())

        invite.refresh_from_db()
        self.assertEqual(invite.accepted_by_id, invited_user.pk)

    def test_expired_invite_cannot_be_accepted(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )
        TeamInvite.objects.filter(pk=invite.pk).update(expires_at=timezone.now() - timedelta(hours=1))

        response = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Invite expired')
        self.assertFalse(TeamMembership.objects.filter(team=self.team, user=self.member).exists())

    def test_already_used_invite_renders_status_without_duplicate_membership(self):
        invite, raw_token = create_team_invite(
            team=self.team,
            email=self.member.email,
            role=TeamMembership.ROLE_MEMBER,
            invited_by=self.owner,
        )

        first = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertRedirects(
            first,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.client.logout()

        second = self.client.get(reverse('accounts:invite_accept', args=[raw_token]))
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'Invite already used')
        self.assertEqual(
            TeamMembership.objects.filter(team=self.team, user=self.member).count(),
            1,
        )

    def test_team_invite_persists_when_email_send_fails(self):
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
        self.assertTrue(
            TeamInvite.objects.filter(
                team=self.team,
                email__iexact=invitee_email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).exists()
        )

    def test_duplicate_active_invite_is_rotated_to_fresh_invite(self):
        self.client.force_login(self.owner)
        invitee_email = 'pending@example.com'

        first = self.client.post(
            reverse('accounts:team_invite', args=[self.team.pk]),
            {
                'email': invitee_email,
                'role': TeamMembership.ROLE_MEMBER,
            },
        )
        first_invite = TeamInvite.objects.get(team=self.team, email__iexact=invitee_email)
        second = self.client.post(
            reverse('accounts:team_invite', args=[self.team.pk]),
            {
                'email': invitee_email,
                'role': TeamMembership.ROLE_MEMBER,
            },
        )

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        first_invite.refresh_from_db()
        self.assertIsNotNone(first_invite.revoked_at)
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
        self.assertEqual(
            TeamInvite.objects.filter(team=self.team, email__iexact=invitee_email).count(),
            2,
        )

    def test_inviting_existing_user_creates_in_app_invite_notification(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse('accounts:team_invite', args=[self.team.pk]),
            {
                'email': self.member.email,
                'role': TeamMembership.ROLE_MEMBER,
            },
        )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        notification = InAppNotification.objects.filter(
            recipient=self.member,
            team=self.team,
            event_type='team.invite.received',
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('/accounts/invites/accept/', notification.link_url)

    def test_invite_notification_still_created_when_email_fails(self):
        self.client.force_login(self.owner)

        with patch('accounts.views.send_team_invite_email', side_effect=RuntimeError('smtp failed')):
            response = self.client.post(
                reverse('accounts:team_invite', args=[self.team.pk]),
                {
                    'email': self.member.email,
                    'role': TeamMembership.ROLE_MEMBER,
                },
            )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(
            TeamInvite.objects.filter(
                team=self.team,
                email__iexact=self.member.email,
                accepted_at__isnull=True,
                revoked_at__isnull=True,
            ).exists()
        )
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.member,
                team=self.team,
                event_type='team.invite.received',
            ).exists()
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

        first_response = self.client.get(reverse('accounts:invite_accept', args=[token_one]))
        second_response = self.client.get(reverse('accounts:invite_accept', args=[token_two]))

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)

        invite_one.refresh_from_db()
        invite_two.refresh_from_db()
        self.assertIsNotNone(invite_one.accepted_at)
        self.assertIsNone(invite_two.accepted_at)
        self.assertIsNotNone(invite_two.revoked_at)

    def test_team_detail_shows_reveal_control_for_non_owner(self):
        self.client.force_login(self.member)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

        response = self.client.get(reverse('accounts:team_detail', args=[self.team.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                'accounts:team_subscription_password',
                args=[self.team.pk, self.team_subscription.pk],
            ),
        )
        self.assertContains(response, 'Create Request')
        self.assertNotContains(response, 'Password: Hidden')
        self.assertNotContains(response, 'secret-password')

    def test_non_owner_sees_pending_requests_without_owner_controls(self):
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)
        TeamSubscriptionRequest.objects.create(
            team=self.team,
            requested_by=self.owner,
            payload={
                'service_name': 'Notion Team',
                'category': 'Software',
                'billing_cycle': 'monthly',
                'cost': '12.00',
                'start_date': timezone.localdate().isoformat(),
                'status': 'active',
                'currency': 'USD',
            },
        )

        self.client.force_login(self.member)
        response = self.client.get(reverse('accounts:team_detail', args=[self.team.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pending Create Requests')
        self.assertContains(response, 'Notion Team')
        self.assertNotContains(response, 'Approve')
        self.assertNotContains(response, 'Reject')

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

    def test_non_owner_can_fetch_team_subscription_password(self):
        self.client.force_login(self.member)
        TeamMembership.objects.create(team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER)

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

    def test_non_owner_creates_pending_team_subscription_request(self):
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
                'account_email': 'member-request@example.com',
                'account_password': 'plaintext-should-not-store',
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
        request_record = TeamSubscriptionRequest.objects.filter(
            team=self.team,
            requested_by=self.member,
            status=TeamSubscriptionRequest.STATUS_PENDING,
        ).first()
        self.assertIsNotNone(request_record)
        self.assertEqual(request_record.payload.get('service_name'), 'Canva')
        self.assertNotIn('account_password', request_record.payload)
        self.assertTrue(
            InAppNotification.objects.filter(
                recipient=self.owner,
                team=self.team,
                event_type='team.request.submitted',
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

    def test_owner_approval_ignores_payload_account_password(self):
        legacy_payload = dict(self.pending_request.payload)
        legacy_payload['account_email'] = 'legacy-team@example.com'
        legacy_payload['account_password'] = 'legacy-plaintext-password'
        self.pending_request.payload = legacy_payload
        self.pending_request.save(update_fields=['payload', 'updated_at'])

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('accounts:team_request_approve', args=[self.pending_request.pk])
        )

        self.assertRedirects(
            response,
            reverse('accounts:team_detail', args=[self.team.pk]),
            fetch_redirect_response=False,
        )
        self.pending_request.refresh_from_db()
        self.assertEqual(self.pending_request.status, TeamSubscriptionRequest.STATUS_APPROVED)
        self.assertIsNotNone(self.pending_request.created_subscription)

        created_subscription = self.pending_request.created_subscription
        created_subscription.refresh_from_db()
        self.assertEqual(created_subscription.account_email, 'legacy-team@example.com')
        self.assertIsNone(created_subscription.account_password)
