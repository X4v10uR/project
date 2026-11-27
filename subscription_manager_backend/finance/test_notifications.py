import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from datetime import UTC, datetime, timedelta
from unittest import skipUnless
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core import mail
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from subscriptions.models import InAppNotification
from subscriptions.notifications import create_notification
from .delivery import deliver_queued, route_notification, send_digests, validate_push
from .models import NotificationDelivery, NotificationPreference, PushSubscription


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class NotificationRegressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('notifications@example.test')
        self.client.force_login(self.user)

    def notification(self, **kwargs):
        return InAppNotification.objects.create(recipient=self.user, title='Alert',
                                                event_type='test', **kwargs)

    def preferences(self, data):
        return self.client.put('/api/finance/notifications/preferences/', data,
                               content_type='application/json')

    def test_partial_quiet_hour_update_uses_existing_other_time(self):
        NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='08:00')
        result = self.preferences({'quiet_end': '09:00'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['quiet_start'], '22:00:00')
        self.assertEqual(result.json()['quiet_end'], '09:00:00')

    def test_cannot_clear_just_one_existing_quiet_hour(self):
        pref = NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='08:00')
        self.assertEqual(self.preferences({'quiet_start': None}).status_code, 400)
        pref.refresh_from_db()
        self.assertIsNotNone(pref.quiet_start)

    @override_settings(VAPID_PUBLIC_KEY='public', VAPID_PRIVATE_KEY='')
    def test_enabling_push_requires_both_server_keys(self):
        self.assertEqual(self.preferences({'push_enabled': True}).status_code, 400)

    def test_snoozing_a_read_alert_makes_it_eligible_to_remind_again(self):
        notification = self.notification(is_read=True, read_at=timezone.now())
        result = self.client.post(f'/api/finance/notifications/{notification.pk}/snooze/',
                                  {'hours': 24}, content_type='application/json')
        self.assertEqual(result.status_code, 200)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)
        self.assertEqual(self.client.get('/api/dashboard/notifications/').json()['unread_count'], 0)

    @patch('subscriptions.notifications.push_created')
    def test_snooze_resurfaces_in_app_during_quiet_hours(self, push):
        now = datetime(2026, 11, 24, 23, tzinfo=UTC)
        NotificationPreference.objects.create(user=self.user, quiet_start='22:00', quiet_end='08:00')
        notification = self.notification()
        InAppNotification.objects.filter(pk=notification.pk).update(created_at=now - timedelta(days=7))
        row = NotificationDelivery.objects.create(notification=notification, email=True,
            deliver_after=now - timedelta(minutes=1), snoozed_until=now - timedelta(minutes=1))
        with patch('finance.delivery.timezone.now', return_value=now), self.captureOnCommitCallbacks(execute=True):
            deliver_queued()
        notification.refresh_from_db()
        self.assertEqual(notification.last_reminded_at, now)
        push.assert_called_once()
        row.refresh_from_db()
        self.assertGreater(row.deliver_after, now)
        self.assertEqual(len(mail.outbox), 0)

    def test_first_digest_failure_preserves_the_original_retry_window(self):
        now = datetime(2026, 11, 24, 12, tzinfo=UTC)
        NotificationPreference.objects.create(user=self.user, digest='daily')
        notification = self.notification()
        InAppNotification.objects.filter(pk=notification.pk).update(created_at=now - timedelta(hours=23))
        with patch('finance.delivery.timezone.now', return_value=now), patch('finance.delivery.send_mail', return_value=0):
            self.assertEqual(send_digests(), 0)
        with patch('finance.delivery.timezone.now', return_value=now + timedelta(hours=2)):
            self.assertEqual(send_digests(), 1)
        self.assertIn(notification.title, mail.outbox[0].body)

    def test_invalid_push_ports_are_validation_errors(self):
        for endpoint in ('https://fcm.googleapis.com:invalid/push', 'https://fcm.googleapis.com:99999/push'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValidationError):
                validate_push(endpoint, {})

    def test_push_key_must_be_a_valid_curve_point(self):
        def encoded(value):
            return base64.urlsafe_b64encode(value).decode().rstrip('=')

        keys = {'auth': encoded(bytes(16)), 'p256dh': encoded(bytes(65))}
        with self.assertRaises(ValidationError):
            validate_push('https://fcm.googleapis.com/push', keys)
        keys['p256dh'] = encoded(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
        validate_push('https://fcm.googleapis.com/push', keys)

    @patch('subscriptions.notifications._send_notification_email')
    @patch('subscriptions.notifications.get_channel_layer', side_effect=RuntimeError('Redis configuration error'))
    def test_websocket_configuration_failure_does_not_prevent_email(self, layer, email):
        with self.captureOnCommitCallbacks(execute=True):
            create_notification(recipient=self.user, event_type='test', title='Email still arrives', send_email_alert=True)
        email.assert_called_once()

    def test_notification_history_pages_include_older_items_without_other_users(self):
        InAppNotification.objects.bulk_create([
            InAppNotification(recipient=self.user, title=f'Alert {index}', event_type='test')
            for index in range(55)
        ])
        other = User.objects.create_user('someone-else@example.test')
        InAppNotification.objects.create(recipient=other, title='Private alert', event_type='test')
        first = self.client.get('/api/dashboard/notifications/').json()
        self.assertEqual(len(first['notifications']), 50)
        self.assertTrue(first['next'])
        self.assertEqual(first['unread_count'], 55)
        second = self.client.get(first['next']).json()
        self.assertEqual(len(second['notifications']), 5)
        self.assertIsNone(second['next'])
        items = first['notifications'] + second['notifications']
        self.assertEqual(len({item['id'] for item in items}), 55)
        self.assertNotIn('Private alert', [item['title'] for item in items])
        legacy = self.client.get('/dashboard/notifications/?page=2')
        self.assertContains(legacy, 'Alert 0')
        self.assertContains(legacy, 'Newer notifications')

    def test_notification_actions_require_ownership_and_valid_snooze_duration(self):
        other = User.objects.create_user('private@example.test')
        notification = InAppNotification.objects.create(recipient=other, title='Private', event_type='test')
        for url in (f'/api/dashboard/notifications/{notification.pk}/read/',
                    f'/api/finance/notifications/{notification.pk}/snooze/'):
            self.assertEqual(self.client.post(url).status_code, 404)
        own = self.notification()
        for hours in (0, 169, 'tomorrow'):
            result = self.client.post(f'/api/finance/notifications/{own.pk}/snooze/',
                                      {'hours': hours}, content_type='application/json')
            self.assertEqual(result.status_code, 400)
        self.assertFalse(NotificationDelivery.objects.filter(notification=own).exists())

    def test_expired_snooze_is_recent_before_the_scheduler_runs(self):
        old = self.notification()
        now = timezone.now()
        InAppNotification.objects.filter(pk=old.pk).update(created_at=now - timedelta(days=7),
                                                          last_reminded_at=now - timedelta(days=2))
        other = self.notification()
        InAppNotification.objects.filter(pk=other.pk).update(created_at=now - timedelta(hours=1))
        until = now - timedelta(minutes=1)
        NotificationDelivery.objects.create(notification=old, deliver_after=until, snoozed_until=until)
        data = self.client.get('/api/dashboard/notifications/').json()
        self.assertEqual([item['id'] for item in data['notifications']], [old.pk, other.pk])
        self.assertEqual(datetime.fromisoformat(data['notifications'][0]['created_at']), until)

    @override_settings(VAPID_PRIVATE_KEY='test-key')
    @patch('pywebpush.webpush')
    def test_push_retry_skips_successful_browsers_and_snooze_resets_them(self, webpush):
        NotificationPreference.objects.create(user=self.user, push_enabled=True)
        second_browser = Client()
        second_browser.force_login(self.user)
        first = PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/first',
            keys={}, session_key=self.client.session.session_key)
        second = PushSubscription.objects.create(user=self.user, endpoint='https://fcm.googleapis.com/second',
            keys={}, session_key=second_browser.session.session_key)
        notification = self.notification()
        webpush.side_effect = [None, RuntimeError('Temporary push failure')]
        route_notification(notification, False)
        row = NotificationDelivery.objects.get(notification=notification)
        self.assertEqual(row.push_delivered, [first.pk])
        self.assertTrue(row.push)
        webpush.side_effect = None
        NotificationDelivery.objects.filter(pk=row.pk).update(deliver_after=timezone.now())
        self.assertEqual(deliver_queued(), 1)
        self.assertEqual([call.kwargs['subscription_info']['endpoint'] for call in webpush.call_args_list],
                         [first.endpoint, second.endpoint, second.endpoint])
        self.client.post(f'/api/finance/notifications/{notification.pk}/snooze/',
                          {'hours': 24}, content_type='application/json')
        self.assertEqual(NotificationDelivery.objects.get(notification=notification).push_delivered, [])
        NotificationDelivery.objects.filter(notification=notification).update(
            deliver_after=timezone.now(), snoozed_until=timezone.now() - timedelta(seconds=1))
        webpush.reset_mock()
        self.assertEqual(deliver_queued(), 1)
        self.assertCountEqual([call.kwargs['subscription_info']['endpoint'] for call in webpush.call_args_list],
                              [first.endpoint, second.endpoint])


@skipUnless(os.name == 'nt', 'Windows Task Scheduler entry point')
class NotificationBatchTests(SimpleTestCase):
    def test_batch_forwards_options_and_preserves_the_scheduler_exit_status(self):
        with TemporaryDirectory(prefix='subly notification batch ') as directory:
            folder = Path(directory)
            script = folder / 'run_notifications.bat'
            shutil.copyfile(Path(__file__).resolve().parents[1] / script.name, script)
            (folder / 'scheduler.py').write_text(
                'import sys\nprint("OPTIONS:", " ".join(sys.argv[1:]))\nsys.exit(7 if "--fail" in sys.argv else 0)\n',
                encoding='utf-8')
            environment = {**os.environ, 'PATH': str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')}
            for options, code in (('--dry-run', 0), ('--time-based --fail', 7)):
                with self.subTest(options=options):
                    result = subprocess.run(f'"{script}" {options}', shell=True, cwd=folder,
                        env=environment, capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    self.assertIn(f'OPTIONS: {options}', result.stdout)
