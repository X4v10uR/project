from datetime import UTC, datetime, timedelta
import os
import runpy
from smtplib import SMTPException
from unittest.mock import patch
from uuid import uuid4

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from accounts.models import Team, TeamMembership, User
from accounts.services import create_team_invite, send_team_invite_email
from finance.delivery import deliver_queued, route_notification, send_digests
from finance.models import NotificationDelivery, NotificationPreference
from subly import settings as project_settings
from subly.emailing import frontend_url
from subscriptions.models import InAppNotification, NotificationLog, Subscription
from subscriptions.notifications import _send_notification_email, create_notification
from subscriptions.services import NotificationService


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SITE_URL='https://subly.example/',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EmailDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('email@example.test', first_name='Alex & Sam')

    def subscription(self, **changes):
        return Subscription.objects.create(**{
            'user': self.user, 'service_name': 'Video & Docs\nPremium <Plus>',
            'category': 'Software', 'cost': '12.00', 'billing_cycle': 'monthly',
            'start_date': timezone.localdate() + timedelta(days=3), **changes,
        })

    def notification(self, **changes):
        return InAppNotification.objects.create(**{
            'recipient': self.user, 'event_type': 'subscription.updated',
            'title': 'Video & Docs\r\nupdated <Plus>', 'body': 'A & B < C',
            'link_url': '/subscriptions/42/edit/?tab=details&source=email', **changes,
        })

    def test_event_zero_send_is_queued_and_retries_without_being_lost(self):
        notification = self.notification()
        with patch('subscriptions.notifications.send_mail', return_value=0):
            route_notification(notification, True)
            row = NotificationDelivery.objects.get(notification=notification)
            self.assertTrue(row.email)
            NotificationDelivery.objects.filter(pk=row.pk).update(deliver_after=timezone.now())
            self.assertEqual(deliver_queued(), 0)
        row.refresh_from_db()
        self.assertTrue(row.email)
        self.assertEqual(row.attempts, 1)
        NotificationDelivery.objects.filter(pk=row.pk).update(deliver_after=timezone.now())
        self.assertEqual(deliver_queued(), 1)
        self.assertFalse(NotificationDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_queued_email_failure_does_not_block_push_delivery(self):
        NotificationPreference.objects.create(user=self.user, push_enabled=True)
        notification = self.notification()
        row = NotificationDelivery.objects.create(notification=notification, email=True, push=True,
            deliver_after=timezone.now())
        with patch('subscriptions.notifications._send_notification_email', side_effect=SMTPException('Unavailable')):
            with patch('finance.delivery.send_push', return_value=True) as push:
                self.assertEqual(deliver_queued(), 0)
        push.assert_called_once_with(notification, delivered=set())
        row.refresh_from_db()
        self.assertTrue(row.email)
        self.assertFalse(row.push)
        self.assertEqual(row.attempts, 1)

    @override_settings(VAPID_PRIVATE_KEY='test-key')
    def test_push_exception_does_not_lose_failed_email_retry(self):
        NotificationPreference.objects.create(user=self.user, push_enabled=True)
        notification = self.notification()
        with patch('subscriptions.notifications._send_notification_email', side_effect=SMTPException('Unavailable')):
            with patch('finance.delivery.send_push', side_effect=RuntimeError('Push unavailable')):
                route_notification(notification, True)
        row = NotificationDelivery.objects.get(notification=notification)
        self.assertTrue(row.email)
        self.assertTrue(row.push)

    def test_event_formats_headers_text_html_and_destination(self):
        _send_notification_email(self.notification())
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'Video & Docs updated <Plus>')
        self.assertIn('Alex & Sam', message.body)
        self.assertIn('A & B < C', message.body)
        url = 'https://subly.example/subscriptions/42/edit/?tab=details&source=email'
        self.assertIn(url, message.body)
        self.assertIn(url.replace('&', '&amp;'), message.alternatives[0].content)
        self.assertIn('A &amp; B &lt; C', message.alternatives[0].content)

    def test_committed_events_and_selected_reminders_use_the_current_address(self):
        sub = self.subscription()
        new_email = 'new@example.test'
        with self.captureOnCommitCallbacks(execute=True):
            create_notification(recipient=self.user, event_type='test', title='Address changed', send_email_alert=True)
            User.objects.filter(pk=self.user.pk).update(email=new_email)
        self.assertTrue(NotificationService.send_renewal_reminder(sub))
        self.assertEqual([m.to for m in mail.outbox], [[new_email], [new_email]])

    def test_deactivation_suppresses_pending_alerts_and_renewals(self):
        sub = self.subscription()
        notification = self.notification()
        NotificationDelivery.objects.create(notification=notification, email=True, deliver_after=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            create_notification(recipient=self.user, event_type='test', title='Pending', send_email_alert=True)
            User.objects.filter(pk=self.user.pk).update(is_active=False)
        deliver_queued()
        self.assertFalse(NotificationService.send_renewal_reminder(sub))
        self.assertFalse(NotificationDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_reminder_rechecks_subscription_changes_after_selection(self):
        for changes in ({'reminders_enabled': False}, {'status': 'cancelled'},
                        {'start_date': timezone.localdate() + timedelta(days=8)}):
            with self.subTest(changes=changes):
                sub = self.subscription()
                Subscription.objects.filter(pk=sub.pk).update(**changes)
                self.assertFalse(NotificationService.send_renewal_reminder(sub))
        self.assertFalse(NotificationLog.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_changed_offsets_invalidate_a_previously_selected_reminder(self):
        sub = self.subscription()
        sub.offsets.create(days_before=3)
        batches = NotificationService.get_subscriptions_due_for_notification()
        self.assertEqual(len(batches), 1)
        sub.offsets.update(days_before=1)
        self.assertFalse(NotificationService.send_renewal_reminder(*batches[0]))
        self.assertFalse(NotificationLog.objects.exists())

    def test_renewal_formats_headers_text_html_and_destination(self):
        sub = self.subscription()
        self.assertTrue(NotificationService.send_renewal_reminder(sub))
        message = mail.outbox[0]
        self.assertIn('Video & Docs Premium <Plus>', message.subject)
        self.assertIn(sub.service_name, message.body)
        self.assertIn('Alex & Sam', message.body)
        self.assertIn(f'https://subly.example/subscriptions/{sub.pk}/edit/', message.body)
        self.assertIn('https://subly.example/planning/alerts/', message.body)
        self.assertIn('Video &amp; Docs', message.alternatives[0].content)

    def test_invitation_handles_multiline_team_names_and_backend_rejection(self):
        team = Team.objects.create(name='Design & Docs\n<Studio>', created_by=self.user)
        invite, token = create_team_invite(team=team, email='guest@example.test', role='member', invited_by=self.user)
        with patch('accounts.services.send_mail', return_value=0):
            with self.assertRaises(RuntimeError):
                send_team_invite_email(invite, token)
        send_team_invite_email(invite, token)
        message = mail.outbox[0]
        self.assertIn('Design & Docs <Studio>', message.subject)
        self.assertIn(team.name, message.body)
        self.assertIn('Design &amp; Docs', message.alternatives[0].content)
        self.assertIn(f'https://subly.example/accounts/invites/accept/{token}/', message.body)

    def test_partial_team_failure_retries_only_failed_recipients(self):
        team = Team.objects.create(name='Team', created_by=self.user)
        members = [self.user, User.objects.create_user('failed@example.test'),
                   User.objects.create_user('later@example.test')]
        for member in members:
            TeamMembership.objects.create(team=team, user=member, role='member')
        sub = self.subscription(team=team)
        send_mail = mail.send_mail

        def partially_send(**kwargs):
            if kwargs['recipient_list'] == [members[1].email]:
                raise SMTPException('Temporary rejection')
            return send_mail(**kwargs)

        with patch('subscriptions.services.send_mail', side_effect=partially_send):
            with self.assertRaises(SMTPException):
                NotificationService.send_renewal_reminder(sub)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(NotificationLog.objects.filter(subscription=sub, delivery_claim=None).count(), 2)
        self.assertEqual(sub.in_app_notifications.count(), 2)
        self.assertTrue(NotificationService.send_renewal_reminder(sub))
        self.assertFalse(NotificationService.send_renewal_reminder(sub))
        self.assertCountEqual([m.to for m in mail.outbox], [[u.email] for u in members])
        self.assertEqual(sub.in_app_notifications.count(), 3)

    def test_rejected_renewal_releases_claim_and_retries(self):
        sub = self.subscription()
        with patch('subscriptions.services.send_mail', return_value=0):
            with self.assertRaises(RuntimeError):
                NotificationService.send_renewal_reminder(sub)
        self.assertFalse(NotificationLog.objects.exists())
        self.assertTrue(NotificationService.send_renewal_reminder(sub))
        self.assertEqual(len(mail.outbox), 1)

    def test_slow_team_batch_does_not_send_after_another_worker_takes_claim(self):
        team = Team.objects.create(name='Team', created_by=self.user)
        member = User.objects.create_user('claimed@example.test')
        for user in (self.user, member):
            TeamMembership.objects.create(team=team, user=user, role='member')
        sub = self.subscription(team=team)
        other_claim = uuid4()

        def send_and_reclaim(**kwargs):
            NotificationLog.objects.filter(subscription=sub, recipient=member).update(delivery_claim=other_claim)
            return 1

        with patch('subscriptions.services.send_mail', side_effect=send_and_reclaim) as send:
            self.assertTrue(NotificationService.send_renewal_reminder(sub))
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs['recipient_list'], [self.user.email])
        self.assertEqual(NotificationLog.objects.get(recipient=member).delivery_claim, other_claim)

    def test_quiet_hours_do_not_duplicate_renewal_emails(self):
        now = datetime(2026, 11, 23, 23, tzinfo=UTC)
        pref = NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='08:00')
        pref.refresh_from_db()
        with patch('finance.delivery.timezone.now', return_value=now):
            sub = self.subscription()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(NotificationService.send_renewal_reminder(sub))
            self.assertEqual(len(mail.outbox), 0)
            self.assertTrue(NotificationDelivery.objects.get().email)
        with patch('finance.delivery.timezone.now', return_value=now + timedelta(hours=10)):
            self.assertEqual(deliver_queued(), 1)
            self.assertFalse(NotificationService.send_renewal_reminder(sub))
        self.assertEqual(len(mail.outbox), 1)

    def test_quiet_hours_end_at_first_valid_time_after_spring_clock_change(self):
        self.user.timezone = 'America/New_York'
        self.user.save(update_fields=['timezone'])
        NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='02:30')
        before = datetime(2026, 3, 8, 6, 30, tzinfo=UTC)  # 1:30 AM before the skipped hour.
        with patch('finance.delivery.timezone.now', return_value=before):
            route_notification(self.notification(), True)
        row = NotificationDelivery.objects.get()
        self.assertEqual(row.deliver_after, datetime(2026, 3, 8, 7, tzinfo=UTC))
        with patch('finance.delivery.timezone.now', return_value=datetime(2026, 3, 8, 7, tzinfo=UTC)):
            self.assertEqual(deliver_queued(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_quiet_hours_in_repeated_hour_never_queue_delivery_in_the_past(self):
        self.user.timezone = 'America/New_York'
        self.user.save(update_fields=['timezone'])
        NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='01:30')
        now = datetime(2026, 11, 1, 6, 15, tzinfo=UTC)  # Second occurrence of 1:15 AM.
        with patch('finance.delivery.timezone.now', return_value=now):
            route_notification(self.notification(), True)
        self.assertEqual(NotificationDelivery.objects.get().deliver_after,
            datetime(2026, 11, 1, 6, 30, tzinfo=UTC))

    def test_digest_preference_replaces_individual_renewal_email(self):
        now = timezone.now().replace(hour=12) + timedelta(days=1)
        NotificationPreference.objects.create(user=self.user, digest='daily')
        with patch('finance.delivery.timezone.now', return_value=now):
            sub = self.subscription()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(NotificationService.send_renewal_reminder(sub))
            self.assertEqual(len(mail.outbox), 0)
            self.assertFalse(NotificationDelivery.objects.exists())
            self.assertEqual(send_digests(), 1)
            self.assertEqual(send_digests(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('summary', mail.outbox[0].subject)

    def test_digest_failure_preserves_checkpoint_for_retry(self):
        now = timezone.now().replace(hour=12) + timedelta(days=1)
        pref = NotificationPreference.objects.create(user=self.user, digest='daily', last_digest_at=now - timedelta(days=1))
        with patch('finance.delivery.timezone.now', return_value=now):
            self.notification()
            for rejection in (0, SMTPException('Unavailable')):
                with self.subTest(rejection=rejection):
                    with patch('finance.delivery.send_mail') as send:
                        if isinstance(rejection, Exception):
                            send.side_effect = rejection
                        else:
                            send.return_value = rejection
                        self.assertEqual(send_digests(), 0)
                    pref.refresh_from_db()
                    self.assertEqual(pref.last_digest_at, now - timedelta(days=1))
            self.assertEqual(send_digests(), 1)
            self.assertEqual(send_digests(), 0)

    def test_digest_checkpoint_does_not_skip_notifications_created_during_send(self):
        now = timezone.now().replace(hour=12) + timedelta(days=1)
        pref = NotificationPreference.objects.create(user=self.user, digest='daily')
        with patch('finance.delivery.timezone.now', return_value=now):
            self.notification(title='First alert')

            def send_and_create(*args, **kwargs):
                with patch('finance.delivery.timezone.now', return_value=now + timedelta(seconds=1)):
                    self.notification(title='Arrived during send')
                return 1

            with patch('finance.delivery.send_mail', side_effect=send_and_create):
                self.assertEqual(send_digests(), 1)
        pref.refresh_from_db()
        self.assertEqual(pref.last_digest_at, now)
        with patch('finance.delivery.timezone.now', return_value=now + timedelta(days=1)):
            self.assertEqual(send_digests(), 1)
        self.assertIn('Arrived during send', mail.outbox[0].body)
        self.assertNotIn('First alert', mail.outbox[0].body)

    def test_digest_rechecks_opt_out_during_batch(self):
        other = User.objects.create_user('second@example.test')
        users = [self.user, other]
        now = datetime(2026, 11, 24, 12, tzinfo=UTC)
        with patch('finance.delivery.timezone.now', return_value=now):
            for user in users:
                self.notification(recipient=user)
                NotificationPreference.objects.create(user=user, digest='daily')

            def send_and_opt_out(subject, message, sender, recipients, **kwargs):
                NotificationPreference.objects.exclude(user__email=recipients[0]).update(email_enabled=False)
                return mail.send_mail(subject, message, sender, recipients, **kwargs)

            with patch('finance.delivery.send_mail', side_effect=send_and_opt_out):
                self.assertEqual(send_digests(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_daily_digest_runs_next_morning_after_a_late_previous_run(self):
        now = datetime(2026, 11, 24, 9, tzinfo=UTC)
        pref = NotificationPreference.objects.create(user=self.user, digest='daily',
            last_digest_at=datetime(2026, 11, 23, 16, tzinfo=UTC))
        with patch('finance.delivery.timezone.now', return_value=now):
            self.notification()
            self.assertEqual(send_digests(), 1)
            self.assertEqual(send_digests(), 0)
        pref.refresh_from_db()
        self.assertEqual(pref.last_digest_at, now)

    def test_digest_schedule_uses_local_dates_across_daylight_saving(self):
        self.user.timezone = 'America/New_York'
        self.user.save(update_fields=['timezone'])
        for digest, previous in (
            ('daily', datetime(2026, 3, 7, 14, tzinfo=UTC)),
            ('weekly', datetime(2026, 3, 1, 14, tzinfo=UTC)),
        ):
            with self.subTest(digest=digest):
                NotificationPreference.objects.update_or_create(user=self.user,
                    defaults={'digest': digest, 'last_digest_at': previous})
                now = datetime(2026, 3, 8, 13, tzinfo=UTC)  # 9 AM after the spring change.
                with patch('finance.delivery.timezone.now', return_value=now):
                    self.notification()
                    self.assertEqual(send_digests(), 1)
                    self.assertEqual(send_digests(), 0)


@override_settings(SITE_URL='https://subly.example/')
class EmailURLTests(SimpleTestCase):
    def test_notification_urls_stay_on_frontend(self):
        for path in ('', 'https://outside.example', '//outside.example', '/\\outside.example', '/\nunsafe'):
            with self.subTest(path=path):
                self.assertEqual(frontend_url(path), 'https://subly.example/dashboard/')


class SMTPSettingsTests(SimpleTestCase):
    def test_ssl_and_starttls_defaults_and_explicit_overrides(self):
        cases = [
            ({}, (587, True, False)),
            ({'EMAIL_USE_SSL': 'True'}, (465, False, True)),
            ({'EMAIL_USE_TLS': 'False', 'EMAIL_PORT': '2525'}, (2525, False, False)),
        ]
        for env, expected in cases:
            with self.subTest(env=env):
                with patch.dict(os.environ), patch('environ.Env.read_env'):
                    for key in ('EMAIL_PORT', 'EMAIL_USE_TLS', 'EMAIL_USE_SSL'):
                        os.environ.pop(key, None)
                    os.environ.update(env)
                    config = runpy.run_path(project_settings.__file__)
                self.assertEqual((config['EMAIL_PORT'], config['EMAIL_USE_TLS'], config['EMAIL_USE_SSL']), expected)
